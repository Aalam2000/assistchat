"""
Маршруты профиля пользователя и настроек OpenAI.
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session as SASession
from src.models import Resource
from src.app.core.db import get_db
from src.app.core.auth import get_current_user
from src.app.core.templates import render_i18n

router = APIRouter()


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, db: SASession = Depends(get_db)):
    """HTML-страница профиля пользователя."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)
    return render_i18n("profile.html", request, "profile", {"user": user})


@router.get("/api/profile/openai")
async def api_profile_openai_get(request: Request, db: SASession = Depends(get_db)):
    """Возвращает OpenAI-настройки пользователя."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    key = getattr(user, "openai_api_key", None)
    masked = (key[:3] + "…" + key[-4:]) if key and len(key) > 7 else "******" if key else None
    return {
        "ok": True,
        "mode": "byok" if key else "managed",
        "key_masked": masked,
        "model": "gpt-4o-mini",
        "history_limit": 20,
        "voice_enabled": False,
    }


@router.post("/api/profile/openai/test")
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
    return {"ok": True}


@router.post("/api/profile/openai/save")
async def api_profile_openai_save(payload: dict, request: Request, db: SASession = Depends(get_db)):
    """Сохраняет OpenAI-ключ в профиле."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    mode = (payload.get("mode") or "byok").lower()
    user.openai_api_key = (payload.get("key") or "").strip() if mode == "byok" else None
    db.add(user)
    db.commit()
    return {"ok": True}
