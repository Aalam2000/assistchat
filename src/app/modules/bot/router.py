"""
src/app/modules/bot/router.py - Глобальный переключатель bot_enabled.
"""

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session as SASession

from src.app.core.auth import get_current_user
from src.app.core.db import get_db
from src.app.modules.bot.guard import (
    count_running_resources,
    stop_user_background_tasks,
)
from src.models.resource import Resource

router = APIRouter()


def _resource_snapshot(row: Resource) -> dict:
    meta = row.meta_json or {}
    creds = meta.get("creds") or {}
    return {
        "id": str(row.id),
        "provider": row.provider,
        "status": row.status,
        "phase": row.phase,
        "has_session": bool(creds.get("string_session")),
        "error": getattr(row, "last_error_code", None),
    }


@router.get("/api/preflight")
async def api_preflight(request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    active = db.query(Resource).filter(
        Resource.user_id == user.id,
        Resource.status == "active",
    ).count()
    return {
        "ok": True,
        "bot_enabled": bool(user.bot_enabled),
        "active_resources": active,
    }


@router.get("/api/bot/status")
async def api_bot_status(request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    running_count = count_running_resources(user.id, db)
    return {
        "ok": True,
        "bot_enabled": bool(user.bot_enabled),
        "running_count": running_count,
    }


@router.post("/api/bot/toggle")
async def api_bot_toggle(request: Request, db: SASession = Depends(get_db)):
    """Меняет bot_enabled; botworker подхватит старт/стоп воркеров."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    user.bot_enabled = not bool(user.bot_enabled)
    db.add(user)
    db.commit()
    db.refresh(user)

    stopped = {}
    if not user.bot_enabled:
        stopped = stop_user_background_tasks(user.id)

    return JSONResponse({
        "ok": True,
        "bot_enabled": user.bot_enabled,
        "stopped": stopped,
    })


@router.get("/api/bot/state")
async def api_bot_state(request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    rows = db.query(Resource).filter_by(user_id=user.id).all()
    resources = [_resource_snapshot(r) for r in rows]
    running_count = count_running_resources(user.id, db)

    return {
        "ok": True,
        "bot_enabled": bool(user.bot_enabled),
        "running_count": running_count,
        "resources": resources,
    }
