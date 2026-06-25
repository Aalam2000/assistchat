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
    resolve_bot_token,
    resolve_tg_creds,
    search_by_name_queries,
)
from src.models.resource import Resource

from src.app.resources.chat_base.run_control import (
    clear_stop,
    is_running,
    is_stop_requested,
    mark_running,
    unmark_running,
)


async def run_search(
    resource_id: str, *, pause_sec: float = 3.0
) -> dict[str, Any]:
    rid = str(resource_id)
    if is_running(rid):
        return {"ok": False, "error": "ALREADY_RUNNING"}

    clear_stop(rid)
    mark_running(rid)
    try:
        return await _run_search_impl(rid, pause_sec=pause_sec)
    finally:
        unmark_running(rid)
        clear_stop(rid)


def _should_stop(rid: str) -> bool:
    return is_stop_requested(rid)


def _finish_run(
    rid: str,
    *,
    status: str,
    message: str,
    queries_completed: list[str],
) -> None:
    db = SessionLocal()
    try:
        row = db.get(Resource, UUID(rid))
        if not row:
            return
        meta = normalize_meta(row.meta_json)
        done = set(meta.get("run", {}).get("queries_done") or [])
        done.update(queries_completed)
        meta["run"]["queries_done"] = sorted(done)
        meta["run"]["last_run_at"] = datetime.now(timezone.utc).isoformat()
        meta["run"]["status"] = status
        meta["run"]["message"] = message
        row.meta_json = meta
        row.phase = "ready"
        db.commit()
    finally:
        db.close()


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
            meta["run"]["message"] = "Выберите ресурс Telegram-сессии"
            row.meta_json = meta
            row.phase = "ready"
            db.commit()
            return {"ok": False, "error": "NO_SESSION"}

        bot_token = resolve_bot_token(db, meta)
        owner_raw = (meta.get("owner") or {}).get("telegram_user_id")
        try:
            owner_id = int(owner_raw)
        except Exception:
            owner_id = 0
        if not bot_token or not owner_id:
            meta["run"]["status"] = "error"
            meta["run"]["message"] = (
                "Выберите Telegram Bot и укажите User ID владельца"
            )
            row.meta_json = meta
            row.phase = "ready"
            db.commit()
            return {"ok": False, "error": "NO_BOT_OR_OWNER"}

        queries = list(meta.get("queries") or [])
        if not queries:
            meta["run"]["status"] = "error"
            meta["run"]["message"] = "Список запросов пуст"
            row.meta_json = meta
            row.phase = "ready"
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

    if not todo:
        _finish_run(
            rid,
            status="done",
            message="nothing_to_do",
            queries_completed=[],
        )
        return {"ok": True, "sent": 0, "skipped": 0}

    sent = 0
    skipped = 0
    cancelled = False
    completed_queries: list[str] = []

    try:
        candidates, completed_queries = await search_by_name_queries(
            creds,
            todo,
            pause_sec=pause_sec,
            should_stop=lambda: _should_stop(rid),
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
                row.phase = "ready"
                db.commit()
        finally:
            db.close()
        return {"ok": False, "error": "SEARCH_FAILED", "detail": str(e)}

    if _should_stop(rid):
        cancelled = True

    for cand in candidates:
        if _should_stop(rid):
            cancelled = True
            break

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

            bot_token = resolve_bot_token(db, meta)
            if not bot_token:
                skipped += 1
                continue
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

    if cancelled:
        _finish_run(
            rid,
            status="stopped",
            message=f"stopped: sent={sent}, skipped={skipped}",
            queries_completed=completed_queries,
        )
        return {"ok": True, "stopped": True, "sent": sent, "skipped": skipped}

    _finish_run(
        rid,
        status="done",
        message=f"sent={sent}, skipped={skipped}",
        queries_completed=todo,
    )
    return {"ok": True, "sent": sent, "skipped": skipped}
