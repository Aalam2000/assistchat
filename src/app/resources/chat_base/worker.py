# src/app/resources/chat_base/worker.py
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from src.app.core.db import SessionLocal
from src.app.resources.chat_base.meta import (
    add_pending,
    is_blocked,
    normalize_meta,
)
from src.app.resources.chat_base.notifier import notifier
from src.app.resources.chat_base.filters import passes_filters
from src.app.resources.chat_base.search import (
    resolve_tg_creds,
    search_by_name_queries,
)
from src.models.resource import Resource

_running: set[str] = set()


def is_running(resource_id: str) -> bool:
    return str(resource_id) in _running


async def run_search(
    resource_id: str, *, pause_sec: float = 3.0
) -> dict[str, Any]:
    rid = str(resource_id)
    if rid in _running:
        return {"ok": False, "error": "ALREADY_RUNNING"}

    _running.add(rid)
    try:
        return await _run_search_impl(rid, pause_sec=pause_sec)
    finally:
        _running.discard(rid)


async def _run_search_impl(rid: str, *, pause_sec: float) -> dict[str, Any]:
    db = SessionLocal()
    try:
        row = db.get(Resource, UUID(rid))
        if not row or row.provider != "chat_base":
            return {"ok": False, "error": "NOT_FOUND"}

        meta = normalize_meta(row.meta_json)
        creds = resolve_tg_creds(db, meta)
        if not creds:
            meta["run"]["status"] = "error"
            meta["run"]["message"] = "Нет Telegram-сессии"
            row.meta_json = meta
            db.commit()
            return {"ok": False, "error": "NO_SESSION"}

        bot_token = (meta.get("creds") or {}).get("bot_token") or ""
        bot_token = str(bot_token).strip()
        owner_raw = (meta.get("owner") or {}).get("telegram_user_id")
        try:
            owner_id = int(owner_raw)
        except Exception:
            owner_id = 0
        if not bot_token or not owner_id:
            meta["run"]["status"] = "error"
            meta["run"]["message"] = (
                "Укажите bot_token и telegram_user_id владельца"
            )
            row.meta_json = meta
            db.commit()
            return {"ok": False, "error": "NO_BOT_OR_OWNER"}

        queries = list(meta.get("queries") or [])
        if not queries:
            meta["run"]["status"] = "error"
            meta["run"]["message"] = "Список запросов пуст"
            row.meta_json = meta
            db.commit()
            return {"ok": False, "error": "NO_QUERIES"}

        filters = meta.get("filters") or {}
        min_members = int(filters.get("min_members") or 0)
        last_post_max_hours = int(filters.get("last_post_max_hours") or 24)
        queries_done = set(meta.get("run", {}).get("queries_done") or [])
        todo = [q for q in queries if q not in queries_done]

        meta["run"]["status"] = "running"
        meta["run"]["message"] = None
        row.meta_json = meta
        db.commit()
    finally:
        db.close()

    sent = 0
    skipped = 0

    try:
        candidates = await search_by_name_queries(
            creds, todo, pause_sec=pause_sec
        )
    except Exception as e:
        db = SessionLocal()
        try:
            row = db.get(Resource, UUID(rid))
            if row:
                meta = normalize_meta(row.meta_json)
                meta["run"]["status"] = "error"
                meta["run"]["message"] = str(e)
                row.meta_json = meta
                db.commit()
        finally:
            db.close()
        return {"ok": False, "error": "SEARCH_FAILED", "detail": str(e)}

    for cand in candidates:
        db = SessionLocal()
        try:
            row = db.get(Resource, UUID(rid))
            if not row:
                break
            meta = normalize_meta(row.meta_json)
            platform = str(meta.get("platform") or "telegram")

            if is_blocked(meta, cand.external_id, platform):
                skipped += 1
                continue

            ok, _reason = passes_filters(
                cand,
                min_members=min_members,
                last_post_max_hours=last_post_max_hours,
            )
            if not ok:
                skipped += 1
                continue

            pending_id = add_pending(meta, cand.to_dict())
            row.meta_json = meta
            db.commit()

            bot_token = str(
                (meta.get("creds") or {}).get("bot_token") or ""
            ).strip()
            owner_id = int((meta.get("owner") or {}).get("telegram_user_id"))
            await notifier.send_candidate(
                resource_id=rid,
                bot_token=bot_token,
                owner_id=owner_id,
                pending_id=pending_id,
                candidate=cand.to_dict(),
            )
            sent += 1
            await asyncio.sleep(1.0)
        finally:
            db.close()

    db = SessionLocal()
    try:
        row = db.get(Resource, UUID(rid))
        if row:
            meta = normalize_meta(row.meta_json)
            done = set(meta.get("run", {}).get("queries_done") or [])
            done.update(todo)
            meta["run"]["queries_done"] = sorted(done)
            meta["run"]["last_run_at"] = datetime.now(timezone.utc).isoformat()
            meta["run"]["status"] = "done"
            meta["run"]["message"] = f"sent={sent}, skipped={skipped}"
            row.meta_json = meta
            row.phase = "ready"
            db.commit()
    finally:
        db.close()

    return {"ok": True, "sent": sent, "skipped": skipped}
