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

# Rate limiting: последняя попытка запроса кода по resource_id
ACTIVATE_ATTEMPTS: dict[str, float] = {}
ACTIVATE_COOLDOWN_SECS = 20  # минимум между попытками отправить код

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


async def _probe_authorized(app_id: int, app_hash: str, string_session: str) -> tuple[bool | None, str | None]:
    """
    Возвращает (authorized, err_message).
    authorized=True  — сессия живая
    authorized=False — сессия мертва (не авторизована)
    authorized=None  — не удалось проверить (FloodWait, таймаут, сеть) — не значит что мертва
    """
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from telethon.errors import FloodWaitError
    except Exception as e:
        return None, f"telethon_import_failed: {e}"

    client = TelegramClient(StringSession(string_session), app_id, app_hash)
    try:
        await asyncio.wait_for(client.connect(), timeout=10)
        ok = await asyncio.wait_for(client.is_user_authorized(), timeout=10)
        return bool(ok), None
    except FloodWaitError as e:
        # Telegram требует паузу — это НЕ значит что сессия мертва
        return None, f"flood_wait:{getattr(e, 'seconds', '?')}"
    except asyncio.TimeoutError:
        return None, "timeout"
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
    else:
        # UI не показывает string_session сразу после активации — не затираем случайно
        old_meta = row.meta_json or {}
        old_creds = (old_meta.get("creds") or {}) if isinstance(old_meta, dict) else {}
        new_creds = meta_json.get("creds") if isinstance(meta_json.get("creds"), dict) else {}
        old_sess = (old_creds.get("string_session") or "").strip()
        new_sess = (new_creds.get("string_session") or "").strip()
        # Никогда не затираем поля активации если UI их не передал
        needs_merge = (old_sess and not new_sess) or any(
            old_creds.get(k) and not new_creds.get(k)
            for k in ("phone_code_hash", "pending_session", "flood_until_ts")
        )
        if needs_merge:
            new_creds = dict(new_creds)
            if old_sess and not new_sess:
                new_creds["string_session"] = old_sess
            for k in ("phone_code_hash", "pending_session", "flood_until_ts"):
                if old_creds.get(k) and not new_creds.get(k):
                    new_creds[k] = old_creds[k]
            meta_json = dict(meta_json)
            meta_json["creds"] = new_creds

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

        if authorized is True:
            row.status = "active"
            row.phase = "starting"
            row.last_error_code = None
            row.error_message = None
            db.add(row)
            db.commit()
            return {"ok": True, "authorized": True, "message": "Сессия активна, ресурс запущен"}

        if authorized is None:
            # FloodWait или таймаут — проверить не удалось, но это НЕ значит что сессия мертва.
            # Включаем ресурс — воркер сам проверит авторизацию при подключении.
            row.status = "active"
            row.phase = "starting"
            row.last_error_code = None
            row.error_message = None
            db.add(row)
            db.commit()
            hint = f" ({err})" if err else ""
            return {
                "ok": True,
                "authorized": True,
                "message": f"Проверка недоступна{hint} — ресурс включён, воркер проверит сессию при подключении.",
            }

        # authorized is False — сессия точно мертва
        row.status = "pause"
        row.phase = "error"
        row.last_error_code = "telegram_not_authorized"
        row.error_message = err or "string_session not authorized"
        db.add(row)
        db.commit()
        return {
            "ok": False,
            "authorized": False,
            "need_reauth": True,
            "message": "Сессия недействительна. Для получения нового кода нажми «Активировать сессию».",
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

    # Rate limiting: не чаще одного запроса кода в ACTIVATE_COOLDOWN_SECS секунд
    last_attempt = ACTIVATE_ATTEMPTS.get(rid, 0)
    if now - last_attempt < ACTIVATE_COOLDOWN_SECS:
        wait_left = ACTIVATE_COOLDOWN_SECS - int(now - last_attempt)
        return {"ok": False, "message": f"Слишком часто. Подождите {wait_left} сек. перед следующей попыткой."}
    ACTIVATE_ATTEMPTS[rid] = now

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

    row.status = "pause"
    row.phase = "paused"
    db.add(row)
    db.commit()
    return {"ok": True, "status": row.status}


@router.post("/{rid}/enable")
async def enable_telegram(
    rid: str,
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Включает ресурс (status=active) если есть string_session."""
    rid_uuid = _uuid(rid)
    row = db.query(Resource).filter(Resource.id == rid_uuid).first()
    if not row or row.user_id != user.id or row.provider != "telegram":
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    meta = row.meta_json or {}
    creds = (meta.get("creds") or {})
    string_session = (creds.get("string_session") or "").strip()
    if not string_session:
        return {
            "ok": False,
            "message": "Нет сохранённой сессии. Сначала активируй через «Активировать сессию».",
        }

    row.status = "active"
    row.phase = "starting"
    row.last_error_code = None
    row.error_message = None
    db.add(row)
    db.commit()
    return {"ok": True, "status": row.status, "message": "Ресурс включён"}


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

    meta = row.meta_json or {}
    raw_creds = meta.get("creds") or {}
    has_session = bool((raw_creds.get("string_session") or "").strip())

    authorized = False
    if probe:
        creds = _get_creds(row)
        row.last_checked_at = _utcnow()
        if not creds:
            row.last_error_code = "telegram_creds_missing"
            row.error_message = "missing app_id/app_hash/string_session"
            row.phase = "error"
            # probe=1 не переводит status в pause — только помечает фазу
            authorized = False
        else:
            app_id, app_hash, string_session = creds
            ok, err = await _probe_authorized(app_id, app_hash, string_session)
            authorized = bool(ok)
            if not authorized:
                row.last_error_code = "telegram_not_authorized" if err is None else "telegram_probe_error"
                row.error_message = err or "string_session not authorized"
                row.phase = "error"
                # НЕ меняем status — пусть пользователь сам решит что делать
            else:
                row.last_error_code = None
                row.error_message = None
        db.add(row)
        db.commit()
        db.refresh(row)
    else:
        # без probe — по воркеру (phase=running значит сессия живая)
        authorized = (row.phase == "running") or (
            has_session and row.status == "active" and row.last_error_code is None
        )

    active = (row.status == "active")
    running = (row.phase == "running")
    return {
        "ok": True,
        "resource_status": row.status,
        "active": active,
        "running": running,
        "has_session": has_session,
        "authorized": bool(authorized),
        "phase": row.phase,
        "last_checked_at": row.last_checked_at.isoformat() if row.last_checked_at else None,
        "last_error_code": row.last_error_code,
        "error_message": row.error_message,
    }
