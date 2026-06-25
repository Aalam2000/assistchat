# src/app/resources/chat_base/router.py
from __future__ import annotations

from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    Form,
    HTTPException,
)
from sqlalchemy.orm import Session as SASession

from src.app.core.auth import get_current_user
from src.app.core.db import get_db
from src.app.resources.chat_base.meta import (
    default_meta,
    normalize_meta,
    suggest_queries,
)
from src.app.resources.chat_base.worker import is_running, run_search
from src.models.resource import Resource

router = APIRouter(prefix="/api/chat_base", tags=["chat_base"])


def _uuid(s: str) -> UUID:
    try:
        return UUID(str(s))
    except Exception:
        raise HTTPException(status_code=400, detail="BAD_ID")


def _get_owned(db: SASession, user, rid: str) -> Resource:
    row = db.query(Resource).filter(Resource.id == _uuid(rid)).first()
    if not row or row.user_id != user.id or row.provider != "chat_base":
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return row


@router.post("/create")
async def create_chat_base(
    label: str = Form(...),
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    r = Resource(
        provider="chat_base",
        user_id=user.id,
        label=(label or "").strip() or "База чатов",
        status="new",
        phase="ready",
        meta_json=default_meta(),
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"ok": True, "id": str(r.id)}


@router.get("/{rid}")
async def get_chat_base(
    rid: str,
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    row = _get_owned(db, user, rid)
    meta = normalize_meta(row.meta_json)
    return {
        "ok": True,
        "id": str(row.id),
        "label": row.label,
        "status": row.status,
        "phase": row.phase,
        "meta_json": meta,
        "running": is_running(str(row.id)),
    }


@router.put("/{rid}")
async def save_chat_base(
    rid: str,
    payload: dict = Body(...),
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    row = _get_owned(db, user, rid)
    label = (payload.get("label") or "").strip() or row.label
    incoming_raw = payload.get("meta_json")
    if not isinstance(incoming_raw, dict):
        incoming_raw = {}

    old = normalize_meta(row.meta_json)
    merged = normalize_meta({**old, **incoming_raw})
    for section in ("filters", "owner", "run", "sources"):
        if isinstance(incoming_raw.get(section), dict):
            merged[section] = {**old.get(section, {}), **incoming_raw[section]}
    if "queries" in incoming_raw:
        merged["queries"] = incoming_raw["queries"]
    for key in ("accepted", "blacklist", "pending"):
        if key not in incoming_raw:
            merged[key] = old.get(key)

    row.label = label
    row.meta_json = merged
    db.add(row)
    db.commit()
    return {"ok": True, "id": str(row.id)}


@router.post("/{rid}/assist")
async def assist_queries(
    rid: str,
    payload: dict = Body(default={}),
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    row = _get_owned(db, user, rid)
    meta = normalize_meta(row.meta_json)
    topic = (payload.get("topic") or meta.get("topic") or "").strip()
    if topic:
        meta["topic"] = topic
    meta["queries"] = suggest_queries(topic)
    row.meta_json = meta
    db.add(row)
    db.commit()
    return {"ok": True, "queries": meta.get("queries") or []}


@router.post("/{rid}/run")
async def start_run(
    rid: str,
    background_tasks: BackgroundTasks,
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    row = _get_owned(db, user, rid)
    if is_running(str(row.id)):
        return {"ok": False, "error": "ALREADY_RUNNING"}
    row.phase = "running"
    db.add(row)
    db.commit()

    background_tasks.add_task(run_search, str(row.id))
    return {"ok": True, "message": "run_started"}


@router.post("/{rid}/reset-queries")
async def reset_queries_done(
    rid: str,
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    row = _get_owned(db, user, rid)
    meta = normalize_meta(row.meta_json)
    meta["run"]["queries_done"] = []
    row.meta_json = meta
    db.add(row)
    db.commit()
    return {"ok": True}
