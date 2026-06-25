# src/app/resources/prompt/router.py
from __future__ import annotations

import os
import shutil
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session as SASession

from src.app.core.auth import get_current_user
from src.app.core.db import get_db
from src.app.resources.chat_base.export import accepted_whitelist_entries
from src.app.resources.chat_base.meta import normalize_meta as normalize_chat_base_meta
from src.app.resources.prompt.backscan import is_running as backscan_is_running
from src.app.resources.prompt.backscan import run_backscan
from src.models.resource import Resource

router = APIRouter(prefix="/api/prompt", tags=["prompt"])

UPLOADS_BASE = Path(os.getenv("UPLOADS_DIR", "/app/uploads"))
ALLOWED_EXT = {".txt", ".pdf", ".docx", ".md"}
MAX_FILE_MB = 10


def _uuid(s: str) -> UUID:
    try:
        return UUID(str(s))
    except Exception:
        raise HTTPException(status_code=400, detail="BAD_ID")


def _default_meta() -> dict:
    return {
        "sources": {
            "telegram_session_rid": None,
            "telegram_bot_rid": None,
            "chat_base_rid": None,
        },
        "owner": {
            "telegram_user_id": None,
        },
        "filters": {
            "reply_private": True,
            "reply_groups": False,
            "reply_channels": False,
            "whitelist": [],
            "blacklist": [],
        },
        "ai": {
            "api_keys_resource_id": None,
            "api_key_field": None,
            "model": None,
        },
        "prompt": {
            "system": "",
            "context": "",
            "context_file": None,
            "steps": [],
            "examples": [],
        },
        "backscan": {
            "days": 7,
            "status": None,
            "message": None,
            "processed": 0,
            "last_run_at": None,
        },
    }


@router.post("/create")
async def create_prompt_resource(
    label: str = Form(...),
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    r = Resource(
        provider="prompt",
        user_id=user.id,
        label=(label or "").strip() or "Промпт",
        status="new",
        phase="paused",
        meta_json=_default_meta(),
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"ok": True, "id": str(r.id)}


@router.put("/{rid}")
async def save_prompt_resource(
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
    if row.provider != "prompt":
        raise HTTPException(status_code=400, detail="BAD_PROVIDER")

    label = (payload.get("label") or "").strip() or row.label or "Промпт"

    incoming = payload.get("meta_json")
    if not isinstance(incoming, dict):
        incoming = {}

    # Merge: не затираем context_file если UI его не передал
    old_meta = row.meta_json or _default_meta()
    old_file = (old_meta.get("prompt") or {}).get("context_file")
    new_file = (incoming.get("prompt") or {}).get("context_file")
    if old_file and not new_file:
        incoming.setdefault("prompt", {})
        incoming["prompt"]["context_file"] = old_file

    row.label = label
    row.meta_json = incoming
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "id": str(row.id)}


@router.post("/{rid}/upload-context")
async def upload_context_file(
    rid: str,
    file: UploadFile = File(...),
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Загрузка файла контекста (txt/pdf/docx/md, до 10 МБ)."""
    rid_uuid = _uuid(rid)
    row = db.query(Resource).filter(Resource.id == rid_uuid).first()
    if not row or row.user_id != user.id or row.provider != "prompt":
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"UNSUPPORTED_FORMAT:{ext}")

    content = await file.read()
    if len(content) > MAX_FILE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail="FILE_TOO_LARGE")

    user_dir = UPLOADS_BASE / str(user.id)
    user_dir.mkdir(parents=True, exist_ok=True)

    # Имя файла привязано к ресурсу — один файл на промпт
    dest = user_dir / f"ctx_{rid}{ext}"
    dest.write_bytes(content)

    # Удаляем старый файл с другим расширением если был
    for old in user_dir.glob(f"ctx_{rid}.*"):
        if old != dest:
            old.unlink(missing_ok=True)

    # Сохраняем путь в meta_json
    meta = row.meta_json or _default_meta()
    meta.setdefault("prompt", {})
    rel_path = str(dest.relative_to(UPLOADS_BASE))
    meta["prompt"]["context_file"] = rel_path
    row.meta_json = meta
    db.add(row)
    db.commit()

    return {"ok": True, "context_file": rel_path, "filename": file.filename, "size": len(content)}


@router.delete("/{rid}/upload-context")
async def delete_context_file(
    rid: str,
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    rid_uuid = _uuid(rid)
    row = db.query(Resource).filter(Resource.id == rid_uuid).first()
    if not row or row.user_id != user.id or row.provider != "prompt":
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    meta = row.meta_json or {}
    rel_path = (meta.get("prompt") or {}).get("context_file")

    if rel_path:
        dest = UPLOADS_BASE / rel_path
        if dest.exists():
            dest.unlink(missing_ok=True)
        meta.setdefault("prompt", {})
        meta["prompt"]["context_file"] = None
        row.meta_json = meta
        db.add(row)
        db.commit()

    return {"ok": True}


@router.post("/{rid}/enable")
async def enable_prompt(
    rid: str,
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    rid_uuid = _uuid(rid)
    row = db.query(Resource).filter(Resource.id == rid_uuid).first()
    if not row or row.user_id != user.id or row.provider != "prompt":
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    meta = row.meta_json or {}
    ai = meta.get("ai") or {}
    if not ai.get("api_keys_resource_id") or not ai.get("api_key_field") or not ai.get("model"):
        return {"ok": False, "message": "Сначала настройте AI-ключ и модель"}

    row.status = "active"
    row.phase = "starting"
    row.last_error_code = None
    row.error_message = None
    db.add(row)
    db.commit()
    return {"ok": True, "status": row.status}


@router.post("/{rid}/stop")
async def stop_prompt(
    rid: str,
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    rid_uuid = _uuid(rid)
    row = db.query(Resource).filter(Resource.id == rid_uuid).first()
    if not row or row.user_id != user.id or row.provider != "prompt":
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    row.status = "pause"
    row.phase = "paused"
    db.add(row)
    db.commit()
    return {"ok": True, "status": row.status}


@router.get("/{rid}/status")
async def prompt_status(
    rid: str,
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    rid_uuid = _uuid(rid)
    row = db.query(Resource).filter(Resource.id == rid_uuid).first()
    if not row or row.user_id != user.id or row.provider != "prompt":
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    meta = row.meta_json or {}
    backscan = meta.get("backscan") or {}

    return {
        "ok": True,
        "resource_status": row.status,
        "active": row.status == "active",
        "running": row.phase == "running",
        "phase": row.phase,
        "last_error_code": row.last_error_code,
        "error_message": row.error_message,
        "backscan_running": backscan_is_running(str(row.id)),
        "backscan": backscan,
    }


@router.post("/{rid}/backscan")
async def start_backscan(
    rid: str,
    background_tasks: BackgroundTasks,
    payload: dict = Body(default={}),
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    rid_uuid = _uuid(rid)
    row = db.query(Resource).filter(Resource.id == rid_uuid).first()
    if not row or row.user_id != user.id or row.provider != "prompt":
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    if backscan_is_running(str(row.id)):
        return {"ok": False, "error": "ALREADY_RUNNING"}
    try:
        days = int(payload.get("days") or 7)
    except Exception:
        days = 7
    days = max(1, min(days, 30))
    background_tasks.add_task(run_backscan, str(row.id), days=days)
    return {"ok": True, "message": "backscan_started", "days": days}


@router.post("/{rid}/import-chat-base")
async def import_chat_base_whitelist(
    rid: str,
    payload: dict = Body(default={}),
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Добавить принятые группы/каналы из chat_base в whitelist промпта."""
    rid_uuid = _uuid(rid)
    row = db.query(Resource).filter(Resource.id == rid_uuid).first()
    if not row or row.user_id != user.id or row.provider != "prompt":
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    cb_raw = payload.get("chat_base_rid")
    if not cb_raw:
        return {"ok": False, "error": "NO_CHAT_BASE"}
    cb_row = db.query(Resource).filter(Resource.id == _uuid(str(cb_raw))).first()
    if (
        not cb_row
        or cb_row.user_id != user.id
        or cb_row.provider != "chat_base"
    ):
        raise HTTPException(status_code=404, detail="CHAT_BASE_NOT_FOUND")

    entries = accepted_whitelist_entries(normalize_chat_base_meta(cb_row.meta_json))
    if not entries:
        return {"ok": False, "error": "NO_ACCEPTED_GROUPS"}

    meta = row.meta_json or _default_meta()
    filters = dict(meta.get("filters") or _default_meta()["filters"])
    wl = [str(x).strip() for x in (filters.get("whitelist") or []) if str(x).strip()]
    seen = {w.lower() for w in wl}
    added = 0
    for entry in entries:
        if entry.lower() in seen:
            continue
        seen.add(entry.lower())
        wl.append(entry)
        added += 1

    filters["whitelist"] = wl
    filters["reply_groups"] = True
    filters["reply_channels"] = True
    meta["filters"] = filters
    sources = dict(meta.get("sources") or {})
    sources["chat_base_rid"] = str(cb_row.id)
    meta["sources"] = sources
    row.meta_json = meta
    db.add(row)
    db.commit()

    return {
        "ok": True,
        "added": added,
        "total": len(wl),
        "whitelist": wl,
    }
