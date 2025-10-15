"""
src/app/modules/bot/router.py - Модуль маршрутов управления ботом AssistChat.
Назначение: предоставить API для предварительной проверки, запуска, остановки и
мониторинга состояния бота, который активирует ресурсы пользователя.
"""

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session as SASession
from src.app.core.db import get_db
from src.app.core.auth import get_current_user
from src.app.modules.bot.manager import bot_manager
from src.models.resource import Resource


router = APIRouter()


# -------------------------------------------------------------------------
# 🌐 Префлайт
# -------------------------------------------------------------------------
@router.get("/api/preflight")
async def api_preflight(request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    return bot_manager.preflight(user.id)


# -------------------------------------------------------------------------
# ▶️ Запуск
# -------------------------------------------------------------------------
@router.post("/api/bot/start")
async def api_bot_start(request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    return await bot_manager.start(user.id)


# -------------------------------------------------------------------------
# ⏸ Остановка
# -------------------------------------------------------------------------
@router.post("/api/bot/stop")
async def api_bot_stop(request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    return await bot_manager.stop(user.id)


# -------------------------------------------------------------------------
# 📊 Статус
# -------------------------------------------------------------------------
@router.get("/api/bot/status")
async def api_bot_status(request: Request, db: SASession = Depends(get_db)):
    """Возвращает текущее состояние бота пользователя."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    active = bool(user.bot_enabled)
    running = user.id in getattr(bot_manager, "workers", {})
    return {"ok": True, "bot_enabled": active, "running": running}


# -------------------------------------------------------------------------
# 🔘 Переключатель БОТа (вкл/выкл)
# -------------------------------------------------------------------------
@router.post("/api/bot/toggle")
async def api_bot_toggle(request: Request, db: SASession = Depends(get_db)):
    """Меняет флаг user.bot_enabled и запускает/останавливает воркеры."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    user.bot_enabled = not bool(user.bot_enabled)
    db.add(user)
    db.commit()
    db.refresh(user)

    if user.bot_enabled:
        result = await bot_manager.start(user.id)
    else:
        result = await bot_manager.stop(user.id)

    return JSONResponse({
        "ok": True,
        "bot_enabled": user.bot_enabled,
        "result": result,
    })

@router.get("/api/bot/state")
async def api_bot_state(request: Request, db: SASession = Depends(get_db)):
    """Возвращает текущее состояние бота и всех ресурсов пользователя."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    # Состояние флага и воркеров
    bot_enabled = bool(user.bot_enabled)
    running = user.id in getattr(bot_manager, "workers", {})

    # Состояние ресурсов пользователя (из БД)
    rows = db.query(Resource).filter_by(user_id=user.id).all()
    resources = []
    for r in rows:
        meta = r.meta_json or {}
        creds = meta.get("creds") or {}
        has_session = bool(creds.get("string_session"))
        resources.append({
            "id": str(r.id),
            "provider": r.provider,
            "status": r.status,
            "phase": r.phase,
            "has_session": has_session,
            "error": getattr(r, "last_error_code", None),
        })

    return {
        "ok": True,
        "bot_enabled": bot_enabled,
        "running": running,
        "resources": resources,
    }
