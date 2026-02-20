# src/app/resources/telegram/router.py
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Body
from sqlalchemy.orm import Session as SASession

from src.app.core.auth import get_current_user
from src.app.core.db import get_db
from src.models.resource import Resource

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


def _uuid(s: str) -> UUID:
    try:
        return UUID(str(s))
    except Exception:
        raise HTTPException(status_code=400, detail="BAD_ID")


def _utcnow():
    return datetime.now(timezone.utc)


def _get_creds(row: Resource) -> tuple[int, str, str] | None:
    meta = row.meta_json or {}
    creds = (meta.get("creds") or {}) or {}

    app_id_raw = creds.get("app_id")
    if isinstance(app_id_raw, str):
        app_id_raw = app_id_raw.strip()
    try:
        app_id = int(app_id_raw)
    except Exception:
        app_id = 0

    app_hash = (creds.get("app_hash") or "").strip()
    string_session = (creds.get("string_session") or "").strip()

    if not app_id or not app_hash or not string_session:
        return None
    return app_id, app_hash, string_session


async def _probe_authorized(app_id: int, app_hash: str, string_session: str) -> tuple[bool, str | None]:
    """Возвращает (authorized, err_message)."""
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
    except Exception as e:
        return False, f"telethon_import_failed: {e}"

    client = TelegramClient(StringSession(string_session), app_id, app_hash)
    try:
        await asyncio.wait_for(client.connect(), timeout=10)
        ok = await asyncio.wait_for(client.is_user_authorized(), timeout=10)
        return bool(ok), None
    except Exception as e:
        return False, str(e)
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


@router.post("/create")
async def create_telegram_resource(
    label: str = Form(...),
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    r = Resource(
        provider="telegram",
        user_id=user.id,
        label=(label or "").strip() or "Telegram",
        status="new",
        phase="paused",
        meta_json={
            "creds": {"app_id": None, "app_hash": "", "phone": "", "string_session": ""},
            "prompt_id": "",
            "ai_keys_resource_id": "",
            "ai_key_field": "creds.openai_api_key",
            "model": "gpt-4o-mini",
            "prefer_voice_reply": True,
            "rules": {"reply_private": True, "reply_groups": False, "reply_channels": False},
            "lists": {"whitelist": [], "blacklist": []},
            "limits": {"tokens_limit": None, "autostop": False},
        },
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"ok": True, "id": str(r.id)}


@router.put("/{rid}")
async def save_telegram_resource(
    rid: str,
    payload: dict = Body(...),
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    rid_uuid = _uuid(rid)
    row = db.query(Resource).filter(Resource.id == rid_uuid).first()
    if not row:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    if row.user_id != user.id:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    if row.provider != "telegram":
        raise HTTPException(status_code=400, detail="BAD_PROVIDER")

    label = (payload.get("label") or "").strip() or row.label or "Telegram"
    meta_json = payload.get("meta_json")
    if meta_json is None or not isinstance(meta_json, dict):
        meta_json = row.meta_json or {}

    row.label = label
    row.meta_json = meta_json

    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "id": str(row.id)}


@router.post("/{rid}/activate")
async def activate_telegram(
    rid: str,
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    rid_uuid = _uuid(rid)
    row = db.query(Resource).filter(Resource.id == rid_uuid).first()
    if not row or row.user_id != user.id or row.provider != "telegram":
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    creds = _get_creds(row)
    if not creds:
        row.status = "pause"
        row.phase = "error"
        row.last_checked_at = _utcnow()
        row.last_error_code = "telegram_creds_missing"
        row.error_message = "missing app_id/app_hash/string_session"
        db.add(row)
        db.commit()
        return {"ok": True, "authorized": False, "status": row.status, "message": "Нет данных сессии"}

    app_id, app_hash, string_session = creds
    authorized, err = await _probe_authorized(app_id, app_hash, string_session)

    row.last_checked_at = _utcnow()
    if not authorized:
        row.status = "pause"  # не даём воркеру стартовать мёртвую сессию
        row.phase = "error"
        row.last_error_code = "telegram_not_authorized" if err is None else "telegram_probe_error"
        row.error_message = err or "string_session not authorized"
        db.add(row)
        db.commit()
        return {"ok": True, "authorized": False, "status": row.status, "message": "Сессия не активна"}

    # Сессия валидна => включаем ресурс для botworker
    row.status = "active"
    row.phase = "starting"
    row.last_error_code = None
    row.error_message = None

    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "authorized": True, "status": row.status, "message": "Сессия активна"}


@router.post("/{rid}/stop")
async def stop_telegram(
    rid: str,
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    rid_uuid = _uuid(rid)
    row = db.query(Resource).filter(Resource.id == rid_uuid).first()
    if not row or row.user_id != user.id or row.provider != "telegram":
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    # Только флаг для botworker. Никаких остановок сессии тут нет.
    row.status = "pause"
    row.phase = "paused"

    db.add(row)
    db.commit()
    return {"ok": True, "status": row.status}


@router.get("/{rid}/status")
async def telegram_status(
    rid: str,
    probe: bool = False,
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    rid_uuid = _uuid(rid)
    row = db.query(Resource).filter(Resource.id == rid_uuid).first()
    if not row or row.user_id != user.id or row.provider != "telegram":
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    authorized = False
    if probe:
        creds = _get_creds(row)
        row.last_checked_at = _utcnow()
        if not creds:
            row.last_error_code = "telegram_creds_missing"
            row.error_message = "missing app_id/app_hash/string_session"
            row.phase = "error"
            row.status = "pause"
            authorized = False
        else:
            app_id, app_hash, string_session = creds
            ok, err = await _probe_authorized(app_id, app_hash, string_session)
            authorized = bool(ok)
            if not authorized:
                row.last_error_code = "telegram_not_authorized" if err is None else "telegram_probe_error"
                row.error_message = err or "string_session not authorized"
                row.phase = "error"
                row.status = "pause"
            else:
                row.last_error_code = None
                row.error_message = None
        db.add(row)
        db.commit()
        db.refresh(row)
    else:
        # без probe — только по последнему чекпоинту
        authorized = (row.last_error_code is None) and (row.last_checked_at is not None)

    active = (row.status == "active")
    running = (row.phase == "running")  # ставит botworker/telegram worker
    return {
        "ok": True,
        "resource_status": row.status,
        "active": active,
        "running": running,
        "authorized": bool(authorized),
        "phase": row.phase,
        "last_checked_at": row.last_checked_at.isoformat() if row.last_checked_at else None,
        "last_error_code": row.last_error_code,
        "error_message": row.error_message,
    }
