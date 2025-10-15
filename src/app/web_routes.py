# src/app/web_routes.py
from fastapi import APIRouter, Request, Depends
from src.app.core.templates import render_i18n, set_lang_en, set_lang_ru
from sqlalchemy import inspect, text
from src.app.core.db import engine, get_db
from src.app.core.auth import get_current_user, require_admin
from src.app.core.templates import render_i18n
from src.models.user import User
from fastapi import Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session as SASession

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
    return render_i18n("profile.html", request, "profile", {"user": user, "username": user.username, "role": user.role.value})



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
# 📱 Telegram ресурс
# -----------------------------------------------------------------------------
@router.get("/resources/telegram/{rid}", response_class=HTMLResponse)
async def resource_telegram_page(rid: str, request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)
    return render_i18n(
        "resources/telegram.html",
        request,
        "resource_telegram",
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

# -----------------------------------------------------------------------------
# 🌐 Переключение языка интерфейса
# -----------------------------------------------------------------------------
@router.get("/set-lang/en")
def switch_lang_en(request: Request):
    return set_lang_en(request)

@router.get("/set-lang/ru")
def switch_lang_ru(request: Request):
    return set_lang_ru(request)

# ────────────────────────────────────────────────────────────────────────────────
# Публичные страницы
# ────────────────────────────────────────────────────────────────────────────────
@router.get("/tables", response_class=HTMLResponse)
async def tables(request: Request, db: SASession = Depends(get_db), _: User = Depends(require_admin)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    data = {}
    with engine.connect() as conn:
        for table in table_names:
            cols = [col["name"] for col in inspector.get_columns(table)]
            rows = conn.execute(text(f'SELECT * FROM "{table}"')).fetchall()
            data[table] = {"columns": cols, "rows": rows}

    return render_i18n(
        "all-tables.html",
        request,
        "tables_index",
        {
            "user": user,
            "username": user.username,
            "role": user.role.value if hasattr(user.role, "value") else str(user.role),
            "data": data,
        },
    )