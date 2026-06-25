# src/app/resources/prompt/backscan.py
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from telethon import TelegramClient, utils
from telethon.sessions import StringSession
from telethon.tl.types import Channel, Chat, User

from src.app.core.db import SessionLocal
from src.app.core.message_bus import MessageEvent
from src.app.resources.chat_base.search import resolve_tg_creds
from src.app.resources.prompt.prompt_worker import (
    PromptWorker,
    _norm_filter_entry,
    _passes_filters,
)
from src.models.resource import Resource

_running: set[str] = set()
MAX_DAYS = 30
MAX_MSGS_PER_CHAT = 500
PAUSE_BETWEEN_CHATS_SEC = 2.0


def is_running(prompt_rid: str) -> bool:
    return str(prompt_rid) in _running


def _peer_type(entity: Any) -> str:
    if isinstance(entity, User):
        return "private"
    if isinstance(entity, Chat):
        return "group"
    if isinstance(entity, Channel):
        return "channel" if entity.broadcast else "group"
    return "chat"


def _chat_id(entity: Any) -> int | None:
    try:
        return int(utils.get_peer_id(entity))
    except Exception:
        return None


def _chat_name(entity: Any) -> str | None:
    if isinstance(entity, User):
        parts = [entity.first_name or "", entity.last_name or ""]
        name = " ".join(p for p in parts if p).strip()
        return name or None
    title = getattr(entity, "title", None)
    return str(title).strip() if title else None


def _msg_type_and_text(msg: Any) -> tuple[str, str]:
    text = (getattr(msg, "message", None) or "").strip()
    if getattr(msg, "photo", None):
        return "photo", text or "[photo]"
    if getattr(msg, "voice", None):
        return "voice", text or "[voice]"
    if getattr(msg, "document", None):
        return "file", text or "[file]"
    return "text", text


def _message_event(
    *,
    session_rid: str,
    session_label: str,
    entity: Any,
    msg: Any,
) -> MessageEvent | None:
    text = (getattr(msg, "message", None) or "").strip()
    msg_type, body = _msg_type_and_text(msg)
    if not body:
        return None

    sender = getattr(msg, "sender", None)
    peer_type = _peer_type(entity)
    chat_id = _chat_id(entity)
    if chat_id is None:
        return None

    sender_id = getattr(sender, "id", None) or chat_id
    sender_username = getattr(sender, "username", None) if sender else None
    chat_username = getattr(entity, "username", None)

    return MessageEvent(
        source_type="telegram_session",
        source_rid=session_rid,
        peer_id=int(sender_id),
        peer_type=peer_type,
        chat_id=int(chat_id),
        sender_username=sender_username,
        msg_id=getattr(msg, "id", None),
        external_chat_id=str(chat_id),
        external_msg_id=str(getattr(msg, "id", "") or ""),
        text=body if msg_type == "text" else text or body,
        msg_type=msg_type,
        source_label=session_label,
        chat_name=_chat_name(entity),
        chat_username=chat_username,
    )


def _update_backscan_meta(
    prompt_rid: str, *, status: str, message: str | None, processed: int = 0
) -> None:
    db = SessionLocal()
    try:
        row = db.get(Resource, UUID(prompt_rid))
        if not row:
            return
        meta = dict(row.meta_json or {})
        scan = dict(meta.get("backscan") or {})
        scan["status"] = status
        scan["message"] = message
        scan["processed"] = processed
        scan["last_run_at"] = datetime.now(timezone.utc).isoformat()
        meta["backscan"] = scan
        row.meta_json = meta
        db.commit()
    finally:
        db.close()


async def run_backscan(prompt_rid: str, *, days: int) -> dict[str, Any]:
    rid = str(prompt_rid)
    if rid in _running:
        return {"ok": False, "error": "ALREADY_RUNNING"}

    days = max(1, min(int(days), MAX_DAYS))
    _running.add(rid)
    processed = 0

    try:
        db = SessionLocal()
        try:
            row = db.get(Resource, UUID(rid))
            if not row or row.provider != "prompt":
                return {"ok": False, "error": "NOT_FOUND"}
            meta = row.meta_json or {}
            sources = meta.get("sources") or {}
            filters = meta.get("filters") or {}
            session_rid = sources.get("telegram_session_rid")
            if not session_rid:
                _update_backscan_meta(
                    rid, status="error", message="Нет Telegram-сессии"
                )
                return {"ok": False, "error": "NO_SESSION"}
            creds = resolve_tg_creds(db, meta)
            if not creds:
                _update_backscan_meta(
                    rid, status="error", message="Сессия недоступна"
                )
                return {"ok": False, "error": "NO_CREDS"}
            whitelist = [
                str(x).strip()
                for x in (filters.get("whitelist") or [])
                if str(x).strip()
            ]
            if not whitelist:
                _update_backscan_meta(
                    rid, status="error", message="Whitelist пуст"
                )
                return {"ok": False, "error": "NO_WHITELIST"}
            steps = (meta.get("prompt") or {}).get("steps") or []
            if not steps:
                _update_backscan_meta(
                    rid, status="error", message="Нет шагов промпта"
                )
                return {"ok": False, "error": "NO_STEPS"}
            session_row = db.get(Resource, UUID(str(session_rid)))
            session_label = (
                (session_row.label if session_row else None) or "Telegram"
            )
        finally:
            db.close()

        _update_backscan_meta(
            rid, status="running", message=f"days={days}", processed=0
        )

        since = datetime.now(timezone.utc) - timedelta(days=days)
        worker = PromptWorker(row)
        app_id, app_hash, string_session = creds
        client = TelegramClient(
            StringSession(string_session), app_id, app_hash
        )
        await client.connect()

        try:
            for entry in whitelist:
                try:
                    target = entry
                    if target.lstrip("-").isdigit():
                        target = int(target)
                    elif not target.startswith("@"):
                        target = f"@{_norm_filter_entry(target)}"
                    entity = await client.get_entity(target)
                except Exception as e:
                    print(f"[BACKSCAN] skip {entry!r}: {e!r}", flush=True)
                    continue

                chat_processed = 0
                async for msg in client.iter_messages(
                    entity, limit=MAX_MSGS_PER_CHAT
                ):
                    if not msg or not getattr(msg, "date", None):
                        continue
                    msg_dt = msg.date
                    if msg_dt.tzinfo is None:
                        msg_dt = msg_dt.replace(tzinfo=timezone.utc)
                    if msg_dt < since:
                        break

                    event = _message_event(
                        session_rid=str(session_rid),
                        session_label=session_label,
                        entity=entity,
                        msg=msg,
                    )
                    if not event:
                        continue
                    if not _passes_filters(
                        event, filters, label=row.label or rid
                    ):
                        continue

                    await worker.process_event(event, ignore_status=True)
                    processed += 1
                    chat_processed += 1
                    await asyncio.sleep(0.3)

                print(
                    f"[BACKSCAN] {entry!r}: processed {chat_processed} msgs",
                    flush=True,
                )
                await asyncio.sleep(PAUSE_BETWEEN_CHATS_SEC)
        finally:
            await client.disconnect()

        msg = f"done: processed={processed}, days={days}"
        _update_backscan_meta(
            rid, status="done", message=msg, processed=processed
        )
        return {"ok": True, "processed": processed, "days": days}
    except Exception as e:
        _update_backscan_meta(
            rid, status="error", message=str(e), processed=processed
        )
        return {"ok": False, "error": "BACKSCAN_FAILED", "detail": str(e)}
    finally:
        _running.discard(rid)
