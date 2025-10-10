from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session as SASession
from src.app.core.db import get_db
from src.app.core.auth import get_current_user
from src.app.core.templates import render_i18n


router = APIRouter()

# -----------------------------------------------------------------------------
# 🏠 Главная страница
# -----------------------------------------------------------------------------
@router.get("/", response_class=HTMLResponse)
async def index_page(request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    return render_i18n(
        "index.html",
        request,
        "index",
        {
            "user": user,
            "username": user.username if user else None,
            "role": user.role.value if user and hasattr(user.role, "value") else str(user.role) if user else None,
        }
    )


# -----------------------------------------------------------------------------
# 👤 Профиль пользователя
# -----------------------------------------------------------------------------
@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)
    return render_i18n(
        "profile.html",
        request,
        "profile",
        {"user": user, "username": user.username}
    )


# -----------------------------------------------------------------------------
# ⚙️ Ресурсы (таблица провайдеров)
# -----------------------------------------------------------------------------
@router.get("/resources", response_class=HTMLResponse)
async def resources_page(request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)
    return render_i18n(
        "resources.html",
        request,
        "resources",
        {"user": user, "username": user.username}
    )


# -----------------------------------------------------------------------------
# 📦 Zoom ресурс
# -----------------------------------------------------------------------------
@router.get("/resources/zoom/{rid}", response_class=HTMLResponse)
async def resource_zoom_page(rid: str, request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)
    return render_i18n(
        "resources/zoom.html",
        request,
        "resource_zoom",
        {"user": user, "username": user.username, "rid": rid}
    )


# -----------------------------------------------------------------------------
# 🧠 AI-страница
# -----------------------------------------------------------------------------
@router.get("/ai", response_class=HTMLResponse)
def ai_page(request: Request):
    user = getattr(request.state, "user", None)
    ctx = {
        "request": request,
        "username": getattr(user, "username", "Гость"),
        "role": getattr(user, "role", "user"),
    }
    return render_i18n("ai.html", request, "ai", ctx)


# -----------------------------------------------------------------------------
# ☎️ Callcenter
# -----------------------------------------------------------------------------
@router.get("/callcenter", response_class=HTMLResponse)
def callcenter_page(request: Request):
    user = getattr(request.state, "user", None)
    ctx = {
        "request": request,
        "username": getattr(user, "username", "Гость"),
        "role": getattr(user, "role", "user"),
    }
    return render_i18n("callcenter.html", request, "callcenter", ctx)


# -----------------------------------------------------------------------------
# 🔲 QR-коды
# -----------------------------------------------------------------------------
@router.get("/qr", response_class=HTMLResponse)
async def qr_page(request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)
    return render_i18n("qr.html", request, "qr", {"username": user.username if user else "Гость"})
