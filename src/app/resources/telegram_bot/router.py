# src/app/resources/telegram_bot/router.py
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Body, Depends, Form, HTTPException
from sqlalchemy.orm import Session as SASession

from src.app.core.auth import get_current_user
from src.app.core.db import get_db
from src.models.resource import Resource

router = APIRouter(prefix="/api/telegram_bot", tags=["telegram_bot"])


def _uuid(s: str) -> UUID:
    try:
        return UUID(str(s))
    except Exception:
        raise HTTPException(status_code=400, detail="BAD_ID")


@router.post("/create")
async def create_bot_resource(
    label: str = Form(...),
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    r = Resource(
        provider="telegram_bot",
        user_id=user.id,
        label=(label or "").strip() or "Telegram Bot",
        status="new",
        phase="paused",
        meta_json={"creds": {"bot_token": ""}},
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"ok": True, "id": str(r.id)}


@router.put("/{rid}")
async def save_bot_resource(
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
    if row.provider != "telegram_bot":
        raise HTTPException(status_code=400, detail="BAD_PROVIDER")

    label = (payload.get("label") or "").strip() or row.label or "Telegram Bot"

    incoming = payload.get("meta_json")
    if not isinstance(incoming, dict):
        incoming = {}

    old_creds = (row.meta_json or {}).get("creds") or {}
    new_creds = incoming.get("creds") if isinstance(incoming.get("creds"), dict) else {}

    # Не затираем bot_token если UI его не передал
    if old_creds.get("bot_token") and not new_creds.get("bot_token"):
        new_creds = dict(new_creds)
        new_creds["bot_token"] = old_creds["bot_token"]

    row.label = label
    row.meta_json = {"creds": new_creds}
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "id": str(row.id)}


@router.post("/{rid}/activate")
async def activate_bot(
    rid: str,
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Проверяет bot_token через getMe и включает ресурс."""
    rid_uuid = _uuid(rid)
    row = db.query(Resource).filter(Resource.id == rid_uuid).first()
    if not row or row.user_id != user.id or row.provider != "telegram_bot":
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    creds = (row.meta_json or {}).get("creds") or {}
    bot_token = (creds.get("bot_token") or "").strip()

    if not bot_token:
        return {"ok": False, "message": "Введи Bot Token"}

    try:
        from aiogram import Bot
        from aiogram.client.default import DefaultBotProperties
        from aiogram.enums import ParseMode

        bot = Bot(token=bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        try:
            me = await bot.get_me()
        finally:
            await bot.session.close()

        row.status = "active"
        row.phase = "starting"
        row.last_error_code = None
        row.error_message = None
        db.add(row)
        db.commit()

        return {
            "ok": True,
            "message": f"Бот @{me.username} подключён",
            "bot_username": me.username,
            "bot_id": me.id,
        }

    except Exception as e:
        row.status = "pause"
        row.phase = "error"
        row.last_error_code = "telegram_bot_invalid_token"
        row.error_message = str(e)
        db.add(row)
        db.commit()
        return {"ok": False, "message": f"Ошибка: {e}"}


@router.post("/{rid}/stop")
async def stop_bot(
    rid: str,
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    rid_uuid = _uuid(rid)
    row = db.query(Resource).filter(Resource.id == rid_uuid).first()
    if not row or row.user_id != user.id or row.provider != "telegram_bot":
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    row.status = "pause"
    row.phase = "paused"
    db.add(row)
    db.commit()
    return {"ok": True, "status": row.status}


@router.post("/{rid}/enable")
async def enable_bot(
    rid: str,
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    rid_uuid = _uuid(rid)
    row = db.query(Resource).filter(Resource.id == rid_uuid).first()
    if not row or row.user_id != user.id or row.provider != "telegram_bot":
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    creds = (row.meta_json or {}).get("creds") or {}
    if not (creds.get("bot_token") or "").strip():
        return {"ok": False, "message": "Сначала сохрани Bot Token и активируй"}

    row.status = "active"
    row.phase = "starting"
    row.last_error_code = None
    row.error_message = None
    db.add(row)
    db.commit()
    return {"ok": True, "status": row.status, "message": "Бот включён"}


@router.get("/{rid}/status")
async def bot_status(
    rid: str,
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    rid_uuid = _uuid(rid)
    row = db.query(Resource).filter(Resource.id == rid_uuid).first()
    if not row or row.user_id != user.id or row.provider != "telegram_bot":
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    creds = (row.meta_json or {}).get("creds") or {}
    has_token = bool((creds.get("bot_token") or "").strip())

    return {
        "ok": True,
        "resource_status": row.status,
        "active": row.status == "active",
        "running": row.phase == "running",
        "has_token": has_token,
        "phase": row.phase,
        "last_error_code": row.last_error_code,
        "error_message": row.error_message,
    }
