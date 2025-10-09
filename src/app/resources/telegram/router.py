"""
Модуль ресурсов: Telegram
Назначение:
    Реализует API для подключения Telegram-аккаунта пользователя как ресурса.
    Поддерживает активацию, подтверждение кода, управление статусом клиента
    и временные in-memory сессии для ожидания подтверждения.
"""

import time
import traceback
from uuid import UUID

from fastapi import APIRouter, Request, HTTPException, Depends, Body
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session as SASession
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, PhoneCodeInvalidError, PhoneNumberInvalidError

from src.app.core.db import get_db
from src.app.core.auth import get_current_user
from src.models import Resource
from src.app.providers import validate_provider_meta

router = APIRouter()

# Кэш ожидающих активацию Telegram-клиентов (живёт в памяти процесса)
PENDING_TG: dict[str, dict] = {}
PENDING_TG_TTL = 300  # 5 минут


@router.post("/api/resource/{rid}/activate")
async def api_resource_activate(
    rid: str,
    request: Request,
    payload: dict = Body(...),
    db: SASession = Depends(get_db),
):
    """
    Основной обработчик активации Telegram-ресурса.
    Шаг 1 — отправка кода (если code не передан),
    Шаг 2 — подтверждение кода (если code передан).
    """
    print(f"[TG_ACT][{rid}] activate called")

    # Проверяем формат UUID
    try:
        rid_uuid = UUID(rid)
    except ValueError:
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    # Проверяем авторизацию пользователя
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False, "error": "UNAUTHORIZED"}, status_code=401)

    row = db.get(Resource, rid_uuid)
    if not row or row.user_id != user.id:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    if row.provider != "telegram":
        return {"ok": False, "error": "NOT_TELEGRAM"}

    meta = row.meta_json or {}
    creds = dict(meta.get("creds") or {})

    phone = payload.get("phone") or creds.get("phone")
    app_id = payload.get("app_id") or creds.get("app_id")
    app_hash = payload.get("app_hash") or creds.get("app_hash")
    code = (payload.get("code") or "").strip() or None

    try:
        app_id = int(app_id)
    except Exception:
        app_id = None

    if not phone or not app_id or not app_hash:
        return {"ok": False, "error": "MISSING_FIELDS"}

    # Если уже активирован — просто подтверждаем статус
    if creds.get("string_session"):
        row.status, row.phase, row.last_error_code = "active", "ready", None
        db.commit()
        return {"ok": True, "activated": True}

    # === Шаг 1: отправка кода ===
    if not code:
        # очищаем старые pending-сессии
        old = PENDING_TG.pop(rid, None)
        if old:
            try:
                await old["client"].disconnect()
            except Exception:
                pass

        client = TelegramClient(StringSession(), app_id, app_hash)
        await client.connect()
        print(f"[TG_ACT][{rid}] client CONNECTED")

        try:
            result = await client.send_code_request(phone)
        except FloodWaitError as e:
            wait_sec = getattr(e, "seconds", 0)
            creds["flood_until_ts"] = int(time.time()) + wait_sec
            meta["creds"] = creds
            row.meta_json, row.phase, row.last_error_code = meta, "error", "FLOOD_WAIT"
            db.commit()
            await client.disconnect()
            return {"ok": False, "error": "FLOOD_WAIT", "wait_seconds": wait_sec}
        except PhoneNumberInvalidError:
            await client.disconnect()
            return {"ok": False, "error": "PHONE_INVALID"}
        except Exception as e:
            traceback.print_exc()
            await client.disconnect()
            return {"ok": False, "error": str(e)}

        creds.update({
            "phone": phone,
            "phone_code_hash": result.phone_code_hash,
            "pending_session": client.session.save()
        })
        meta["creds"] = creds
        row.meta_json, row.phase, row.last_error_code = meta, "waiting_code", None
        db.commit()

        PENDING_TG[rid] = {
            "client": client,
            "session": creds["pending_session"],
            "phone": phone,
            "app_id": app_id,
            "app_hash": app_hash,
            "sent_code": result,
            "ts": time.time(),
        }
        print(f"[TG_ACT][{rid}] waiting for code")
        return {"ok": True, "need_code": True}

    # === Шаг 2: подтверждение кода ===
    entry = PENDING_TG.get(rid)
    creds = dict((row.meta_json or {}).get("creds") or {})
    phone_code_hash = creds.get("phone_code_hash")
    pending_session = creds.get("pending_session")
    if not phone_code_hash:
        return {"ok": False, "error": "MISSING_PHONE_CODE_HASH"}

    if entry and time.time() - entry["ts"] <= PENDING_TG_TTL:
        client = entry["client"]
        try:
            await client.sign_in(code=code)
            final_session = client.session.save()
        except PhoneCodeInvalidError:
            return {"ok": False, "error": "CODE_INVALID"}
    else:
        if not pending_session:
            return {"ok": False, "error": "MISSING_PENDING_SESSION"}
        client = TelegramClient(StringSession(pending_session), app_id, app_hash)
        await client.connect()
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
            final_session = client.session.save()
        except PhoneCodeInvalidError:
            return {"ok": False, "error": "CODE_INVALID"}

    creds["string_session"] = final_session
    creds.pop("phone_code_hash", None)
    creds.pop("pending_session", None)
    meta["creds"] = creds
    row.meta_json, row.status, row.phase, row.last_error_code = meta, "active", "ready", None
    db.commit()
    await client.disconnect()
    PENDING_TG.pop(rid, None)
    return {"ok": True, "activated": True}
