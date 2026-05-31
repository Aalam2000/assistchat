# src/app/resources/telegram/router.py
from __future__ import annotations

import asyncio
import time
import traceback
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Body
from sqlalchemy.orm import Session as SASession

from src.app.core.auth import get_current_user
from src.app.core.db import get_db
from src.models.resource import Resource

# Живые клиенты ожидающие код подтверждения (только в памяти, fallback через БД)
PENDING_TG: dict[str, dict] = {}
PENDING_TG_TTL = 300  # 5 минут

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
    payload: dict = Body(default={}),
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon.errors import FloodWaitError, PhoneCodeInvalidError, PhoneNumberInvalidError

    rid_uuid = _uuid(rid)
    row = db.query(Resource).filter(Resource.id == rid_uuid).first()
    if not row or row.user_id != user.id or row.provider != "telegram":
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    meta = row.meta_json or {}
    creds = dict(meta.get("creds") or {})

    # Читаем поля
    app_id_raw = creds.get("app_id")
    try:
        app_id = int(app_id_raw) if app_id_raw else None
    except Exception:
        app_id = None

    app_hash = (creds.get("app_hash") or "").strip() or None
    phone = (creds.get("phone") or "").strip() or None
    string_session = (creds.get("string_session") or "").strip() or None
    code = (payload.get("code") or "").strip() or None

    print(f"[TG_ACT][{rid}] app_id={app_id} app_hash={'SET' if app_hash else 'NONE'} "
          f"phone={phone} string_session={'SET' if string_session else 'NONE'} code={'SET' if code else 'NONE'}")

    # ── Если string_session есть → проверяем реальную живость ──
    if string_session and not code:
        if not app_id or not app_hash:
            return {"ok": False, "message": "Не хватает App ID или App Hash"}

        authorized, err = await _probe_authorized(app_id, app_hash, string_session)
        row.last_checked_at = _utcnow()

        if authorized:
            row.status = "active"
            row.phase = "starting"
            row.last_error_code = None
            row.error_message = None
            db.add(row)
            db.commit()
            return {"ok": True, "authorized": True, "message": "Сессия активна, ресурс запущен"}
        else:
            # Сессия мертва — сбрасываем string_session, предлагаем пересоздать
            creds["string_session"] = ""
            meta["creds"] = creds
            row.meta_json = meta
            row.status = "pause"
            row.phase = "error"
            row.last_error_code = "telegram_not_authorized"
            row.error_message = err or "string_session not authorized"
            db.add(row)
            db.commit()
            return {
                "ok": False,
                "authorized": False,
                "message": f"Сессия недействительна: {err or 'не авторизована'}. Нажми Активировать снова — запросим новый код.",
            }

    # ── Нет string_session: проверяем что есть всё для запроса кода ──
    if not app_id or not app_hash or not phone:
        missing = []
        if not app_id:
            missing.append("App ID")
        if not app_hash:
            missing.append("App Hash")
        if not phone:
            missing.append("номер телефона")
        return {"ok": False, "message": f"Не хватает: {', '.join(missing)}"}

    # ── ШАГ 2: принимаем код подтверждения ──
    if code:
        phone_code_hash = creds.get("phone_code_hash")
        pending_session = creds.get("pending_session")
        if not phone_code_hash:
            return {"ok": False, "message": "Нет phone_code_hash в БД — начни активацию заново"}

        entry = PENDING_TG.get(rid)
        if entry and (time.time() - entry.get("ts", 0) <= PENDING_TG_TTL):
            # живой клиент в памяти
            client = entry["client"]
            print(f"[TG_ACT][{rid}] step2: reuse alive client from memory")
            try:
                await client.sign_in(code=code)
                final_session = client.session.save()
                print(f"[TG_ACT][{rid}] sign_in SUCCESS (memory client)")
            except PhoneCodeInvalidError:
                return {"ok": False, "message": "Неверный код подтверждения"}
            except Exception as e:
                traceback.print_exc()
                return {"ok": False, "message": f"Ошибка входа: {e}"}
        else:
            # fallback: клиент потерян (рестарт сервера), восстанавливаем из pending_session в БД
            if not pending_session:
                return {"ok": False, "message": "Сессия ожидания потеряна — начни активацию заново"}
            client = TelegramClient(StringSession(pending_session), app_id, app_hash)
            await client.connect()
            print(f"[TG_ACT][{rid}] step2: fallback client from pending_session")
            try:
                await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
                final_session = client.session.save()
                print(f"[TG_ACT][{rid}] sign_in SUCCESS (fallback)")
            except PhoneCodeInvalidError:
                return {"ok": False, "message": "Неверный код подтверждения"}
            except Exception as e:
                traceback.print_exc()
                return {"ok": False, "message": f"Ошибка входа: {e}"}

        # Сохраняем string_session, чистим временные поля
        creds["string_session"] = final_session
        creds.pop("phone_code_hash", None)
        creds.pop("pending_session", None)
        meta["creds"] = creds
        row.meta_json = meta
        row.status = "active"
        row.phase = "starting"
        row.last_error_code = None
        row.error_message = None
        db.add(row)
        db.commit()
        print(f"[TG_ACT][{rid}] FINAL: string_session saved, len={len(final_session)}")

        try:
            await client.disconnect()
        except Exception:
            pass
        finally:
            PENDING_TG.pop(rid, None)

        return {"ok": True, "authorized": True, "message": "Telegram активирован успешно"}

    # ── ШАГ 1: отправляем код на телефон ──
    now = int(time.time())
    flood_until = int(creds.get("flood_until_ts") or 0)
    if flood_until and flood_until > now:
        wait_left = flood_until - now
        return {"ok": False, "message": f"Слишком много попыток, подожди {wait_left} сек."}

    # Зачищаем старый pending клиент если был
    old = PENDING_TG.pop(rid, None)
    if old:
        try:
            await old["client"].disconnect()
        except Exception:
            pass

    client = TelegramClient(StringSession(), app_id, app_hash)
    await client.connect()
    print(f"[TG_ACT][{rid}] step1: connected, sending code to {phone}")

    try:
        result = await client.send_code_request(phone)
        print(f"[TG_ACT][{rid}] send_code_request OK, hash={result.phone_code_hash}")
    except FloodWaitError as e:
        wait_sec = getattr(e, "seconds", 60)
        creds["flood_until_ts"] = int(time.time()) + int(wait_sec)
        meta["creds"] = creds
        row.meta_json = meta
        row.phase = "error"
        row.last_error_code = "FLOOD_WAIT"
        db.add(row)
        db.commit()
        await client.disconnect()
        return {"ok": False, "message": f"Слишком много попыток, подожди {wait_sec} сек."}
    except PhoneNumberInvalidError:
        await client.disconnect()
        return {"ok": False, "message": "Неверный номер телефона"}
    except Exception as e:
        traceback.print_exc()
        await client.disconnect()
        return {"ok": False, "message": f"Ошибка отправки кода: {e}"}

    # Сохраняем в БД промежуточные данные
    pending_session = client.session.save()
    creds["phone_code_hash"] = result.phone_code_hash
    creds["pending_session"] = pending_session
    creds.pop("flood_until_ts", None)
    meta["creds"] = creds
    row.meta_json = meta
    row.phase = "waiting_code"
    row.last_error_code = None
    db.add(row)
    db.commit()

    # Держим живой клиент в памяти для шага 2
    PENDING_TG[rid] = {
        "client": client,
        "ts": time.time(),
    }
    print(f"[TG_ACT][{rid}] step1 OK → waiting_code. pending_session_len={len(pending_session)}")

    return {"ok": True, "need_code": True, "message": "Код отправлен в Telegram"}


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
