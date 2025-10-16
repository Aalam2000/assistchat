"""
src/app/resources/telegram/router.py
────────────────────────────────────
API-обработчики для работы с Telegram-ресурсом.

Назначение:
    • Привязка Telegram-аккаунта пользователя к ресурсу AssistChat;
    • Отправка и подтверждение кода авторизации (через Telethon);
    • Обновление статуса и данных ресурса в таблице resources.
"""

import time
import traceback
from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Depends, Body
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session as SASession
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, PhoneCodeInvalidError, PhoneNumberInvalidError

from src.app.core.db import get_db
from src.app.core.auth import get_current_user
from src.models import Resource

from sse_starlette.sse import EventSourceResponse
import asyncio

router = APIRouter()

# временное хранилище клиентов, ожидающих подтверждения кода
PENDING_TG: dict[str, dict] = {}
PENDING_TG_TTL = 300  # 5 минут
# Слушатели для событий ресурсов (Server-Sent Events)
# Каждый слушатель — asyncio.Queue, в которую кладутся уведомления.
RESOURCE_LISTENERS: set[asyncio.Queue] = set()

async def _notify_resource_update():
    """Отправить событие update всем активным слушателям."""
    for queue in list(RESOURCE_LISTENERS):
        try:
            await queue.put("data: update\n\n")
        except Exception:
            RESOURCE_LISTENERS.discard(queue)

@router.post("/api/resource/{rid}/activate")
async def api_resource_activate(
    rid: str,
    request: Request,
    payload: dict = Body(...),
    db: SASession = Depends(get_db),
):
    """
    Активация Telegram-ресурса:
      • шаг 1 — отправка кода подтверждения;
      • шаг 2 — подтверждение кода и сохранение string_session.
    """

    print(f"[TG_ACT][{rid}] activate called")

    # ── Проверяем корректность ID ресурса ─────────────────────────
    try:
        rid_uuid = UUID(rid)
    except ValueError:
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    # ── Получаем текущего пользователя ────────────────────────────
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False, "error": "UNAUTHORIZED"}, status_code=401)

    # ── Проверяем наличие ресурса ─────────────────────────────────
    row = db.get(Resource, rid_uuid)
    if not row or row.user_id != user.id:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    if row.provider != "telegram":
        return {"ok": False, "error": "NOT_TELEGRAM"}

    print(f"[TG_ACT][{rid}] bot_enabled={getattr(user, 'bot_enabled', None)} (ignored for activation)")

    meta = row.meta_json or {}
    creds = dict(meta.get("creds") or {})

    phone = (payload.get("phone") or creds.get("phone") or "").strip()
    app_id = payload.get("app_id") or creds.get("app_id")
    app_hash = payload.get("app_hash") or creds.get("app_hash")
    code = (payload.get("code") or "").strip() or None

    try:
        app_id = int(app_id)
    except Exception:
        app_id = None

    # если это шаг 2 (пришёл code), разрешаем использовать уже сохранённые данные
    if not code and (not phone or not app_id or not app_hash):
        return {"ok": False, "error": "MISSING_FIELDS"}

    # ── Если уже активирован ──────────────────────────────────────
    if creds.get("string_session"):
        row.status = "active"
        row.phase = "ready"
        row.last_error_code = None
        row.last_activity = datetime.now(timezone.utc)
        db.commit()
        return {"ok": True, "activated": True}

    # === ШАГ 1: отправка кода =====================================
    if not code:
        # закрываем старую pending-сессию
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
            row.meta_json = meta
            row.phase = "error"
            row.last_error_code = "FLOOD_WAIT"
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
            "pending_session": client.session.save(),
        })
        meta["creds"] = creds
        row.meta_json = meta
        row.phase = "waiting_code"
        row.last_error_code = None
        db.commit()
        db.refresh(row)

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

    # === ШАГ 2: подтверждение кода ================================
    entry = PENDING_TG.get(rid)
    creds = dict((row.meta_json or {}).get("creds") or {})
    phone_code_hash = creds.get("phone_code_hash")
    pending_session = creds.get("pending_session")
    if not phone_code_hash:
        return {"ok": False, "error": "MISSING_PHONE_CODE_HASH"}

    # подключаемся к клиенту
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

    # ── Сохраняем итоговую сессию ─────────────────────────────────
    creds["string_session"] = final_session
    creds.pop("phone_code_hash", None)
    creds.pop("pending_session", None)
    meta["creds"] = creds
    row.meta_json = meta
    row.status = "ready"
    row.phase = "waiting_start"
    row.last_error_code = None
    row.last_activity = datetime.now(timezone.utc)
    db.commit()
    await _notify_resource_update()

    # закрываем соединение и очищаем временные данные
    try:
        await client.disconnect()
    except Exception:
        pass
    PENDING_TG.pop(rid, None)

    print(f"[TG_ACT][{rid}] activation complete")
    return {"ok": True, "activated": True}

@router.post("/api/resources/toggle")
async def api_resources_toggle(
    data: dict = Body(...),
    db: SASession = Depends(get_db),
):
    """Включение/выключение ресурса (из Telegram.js)."""
    rid = data.get("id")
    action = data.get("action")

    if not rid or action not in {"activate", "pause"}:
        return JSONResponse({"ok": False, "error": "BAD_REQUEST"}, status_code=400)

    try:
        rid_uuid = UUID(rid)
    except ValueError:
        return JSONResponse({"ok": False, "error": "INVALID_ID"}, status_code=400)

    row = db.get(Resource, rid_uuid)
    if not row:
        return JSONResponse({"ok": False, "error": "NOT_FOUND"}, status_code=404)

    if action == "activate":
        row.status = "active"
        row.phase = "running"
    else:
        row.status = "paused"
        row.phase = "ready"

    row.last_activity = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)

    # оповещаем SSE-слушателей
    await _notify_resource_update()

    print(f"[TG_RES_TOGGLE] {row.label} → {row.status}")
    return {"ok": True, "status": row.status, "phase": row.phase}


@router.get("/api/stream/resources")
async def stream_resources(request: Request):
    """Поток событий обновления ресурсов (SSE)."""
    queue = asyncio.Queue()
    RESOURCE_LISTENERS.add(queue)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                msg = await queue.get()
                yield msg
        finally:
            RESOURCE_LISTENERS.discard(queue)

    return EventSourceResponse(event_generator())

