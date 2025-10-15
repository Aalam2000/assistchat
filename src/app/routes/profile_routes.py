"""
src/app/routes/profile_routes.py - Маршруты профиля пользователя и настроек OpenAI.
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session as SASession
from src.app.core.db import get_db
from src.app.core.auth import get_current_user

router = APIRouter(prefix="/api/profile", tags=["profile-api"])


@router.get("/openai")
async def api_profile_openai_get(request: Request, db: SASession = Depends(get_db)):
    """Возвращает OpenAI-настройки пользователя."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    key = getattr(user, "openai_api_key", None)
    masked = (key[:3] + "…" + key[-4:]) if key and len(key) > 7 else "******" if key else None
    mode = request.cookies.get("openai_mode") or ("byok" if key else "managed")
    return {
        "ok": True,
        "mode": mode,
        "key_masked": masked,
        "model": "gpt-4o-mini",
        "history_limit": 20,
        "voice_enabled": request.cookies.get("voice_enabled") == "1",
    }


@router.post("/openai/test")
async def api_profile_openai_test(payload: dict, request: Request, db: SASession = Depends(get_db)):
    """Минимальная валидация ключа OpenAI."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    mode = (payload.get("mode") or "byok").lower()
    if mode == "byok":
        key = (payload.get("key") or "").strip()
        if not key.startswith("sk-") or len(key) < 20:
            return JSONResponse({"ok": False, "error": "KEY_FORMAT"}, status_code=400)
    return {"ok": True, "message": "Ключ проверен"}


@router.post("/openai/save")
async def api_profile_openai_save(payload: dict, request: Request, db: SASession = Depends(get_db)):
    """Сохраняет OpenAI-ключ и выбранный режим."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    mode = (payload.get("mode") or "byok").lower()
    key = (payload.get("key") or "").strip() if mode == "byok" else None
    user.openai_api_key = key
    db.add(user)
    db.commit()

    resp = JSONResponse({"ok": True})
    resp.set_cookie("openai_mode", mode, httponly=True, samesite="lax")
    resp.set_cookie("voice_enabled", "1" if payload.get("voice_enabled") else "0", httponly=True, samesite="lax")
    return resp
