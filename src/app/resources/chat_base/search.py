# src/app/resources/chat_base/search.py
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import UUID

from sqlalchemy.orm import Session as SASession
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.types import Channel, Chat

from src.app.resources.chat_base.filters import GroupCandidate
from src.models.resource import Resource


def resolve_tg_creds(
    db: SASession, meta: dict[str, Any]
) -> tuple[int, str, str] | None:
    sources = meta.get("sources") or {}
    sid_raw = sources.get("telegram_session_rid")
    if not sid_raw:
        return None
    try:
        sid = UUID(str(sid_raw))
    except Exception:
        return None
    row = db.get(Resource, sid)
    if (
        not row
        or row.provider != "telegram"
        or not isinstance(row.meta_json, dict)
    ):
        return None
    linked = row.meta_json.get("creds") or {}
    app_id = linked.get("app_id")
    app_hash = (linked.get("app_hash") or "").strip()
    string_session = (linked.get("string_session") or "").strip()
    try:
        app_id_int = int(app_id)
    except Exception:
        return None
    if not app_hash or not string_session:
        return None
    return app_id_int, app_hash, string_session


def resolve_bot_token(db: SASession, meta: dict[str, Any]) -> str | None:
    sources = meta.get("sources") or {}
    bid_raw = sources.get("telegram_bot_rid")
    if not bid_raw:
        return None
    try:
        bid = UUID(str(bid_raw))
    except Exception:
        return None
    row = db.get(Resource, bid)
    if (
        not row
        or row.provider != "telegram_bot"
        or not isinstance(row.meta_json, dict)
    ):
        return None
    token = (row.meta_json.get("creds") or {}).get("bot_token") or ""
    token = str(token).strip()
    return token or None


def _link(username: str | None, chat_id: int | None) -> str | None:
    if username:
        return f"https://t.me/{username.lstrip('@')}"
    return None


def _eid(username: str | None, chat_id: int | None) -> str:
    if username:
        return f"@{username.lstrip('@')}"
    return str(chat_id or "")


async def _week_stats(
    client: TelegramClient, entity: Any
) -> tuple[datetime | None, int]:
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    last_post_at: datetime | None = None
    week_count = 0
    try:
        async for msg in client.iter_messages(entity, limit=300):
            if not msg or not msg.date:
                continue
            msg_dt = msg.date
            if msg_dt.tzinfo is None:
                msg_dt = msg_dt.replace(tzinfo=timezone.utc)
            if last_post_at is None:
                last_post_at = msg_dt
            if msg_dt < week_ago:
                break
            week_count += 1
    except Exception:
        pass
    return last_post_at, week_count


async def _description(client: TelegramClient, entity: Any) -> str | None:
    try:
        full = await client.get_entity(entity)
        about = getattr(full, "about", None)
        if about:
            return str(about).strip()
    except Exception:
        pass
    return None


async def search_by_name_queries(
    creds: tuple[int, str, str],
    queries: list[str],
    *,
    pause_sec: float = 3.0,
    should_stop: Callable[[], bool] | None = None,
) -> tuple[list[GroupCandidate], list[str]]:
    app_id, app_hash, string_session = creds
    client = TelegramClient(StringSession(string_session), app_id, app_hash)
    found: dict[str, GroupCandidate] = {}
    completed: list[str] = []
    await client.connect()
    try:
        for query in queries:
            if should_stop and should_stop():
                break
            q = (query or "").strip()
            if not q:
                continue
            try:
                result = await client(SearchRequest(q=q, limit=50))
            except Exception:
                await asyncio.sleep(pause_sec)
                continue

            chats = list(getattr(result, "chats", []) or [])
            for chat in chats:
                if should_stop and should_stop():
                    break
                if not isinstance(chat, (Channel, Chat)):
                    continue
                title = getattr(chat, "title", None) or ""
                username = getattr(chat, "username", None)
                chat_id = getattr(chat, "id", None)
                eid = _eid(username, chat_id)
                if not eid or eid in found:
                    continue

                members = getattr(chat, "participants_count", None)
                try:
                    entity = await client.get_entity(chat)
                    if members is None:
                        members = getattr(entity, "participants_count", None)
                except Exception:
                    entity = chat

                desc = await _description(client, entity)
                last_post_at, week_count = await _week_stats(client, entity)

                found[eid] = GroupCandidate(
                    external_id=eid,
                    title=title,
                    link=_link(username, chat_id),
                    members=int(members) if members is not None else None,
                    description=desc,
                    last_post_at=last_post_at,
                    week_message_count=week_count,
                    query=q,
                )
            completed.append(q)
            if should_stop and should_stop():
                break
            await asyncio.sleep(pause_sec)
    finally:
        await client.disconnect()
    return list(found.values()), completed
