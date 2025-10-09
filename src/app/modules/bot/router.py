"""
Модуль маршрутов управления ботом AssistChat.
Назначение: предоставить API для предварительной проверки, запуска, остановки и
мониторинга состояния бота, который активирует ресурсы пользователя.
"""

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from src.app.core.db import get_db
from src.app.core.auth import get_current_user
from src.app.modules.bot.manager import bot_manager
from sqlalchemy.orm import Session as SASession

router = APIRouter()

@router.get("/api/preflight")
async def api_preflight(request: Request, db: SASession = Depends(get_db)):
    """Предварительная проверка состояния перед запуском бота."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    return bot_manager.preflight(user.id)


@router.post("/api/bot/start")
async def api_bot_start(request: Request, db: SASession = Depends(get_db)):
    """Запуск бота для текущего пользователя."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    return await bot_manager.start(user.id)


@router.post("/api/bot/stop")
async def api_bot_stop(request: Request, db: SASession = Depends(get_db)):
    """Остановка всех активных ресурсов пользователя."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    return await bot_manager.stop(user.id)


@router.get("/api/bot/status")
async def api_bot_status():
    """Возвращает количество активных рабочих экземпляров бота."""
    return {"ok": True, "running": len(getattr(bot_manager, "workers", {}))}
