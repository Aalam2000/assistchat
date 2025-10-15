"""
src/app/main.py - Главный модуль приложения AssistChat.
Назначение: собрать FastAPI-приложение, подключив ядро, модули и ресурсы.
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from src.app.core.config import BASE_DIR, SESSION_SECRET, STATIC_DIR
# ядро
from src.app.core.middleware import _authflow_trace
from src.app.modules.bot.router import router as bot_router
from src.app.modules.qr.router import router as qr_router
from src.app.resources.common import router as resources_router
from src.app.resources.telegram.router import router as telegram_router
from src.app.resources.zoom.router import router as zoom_router
from src.app.routes.auth_routes import router as auth_router
# маршруты
from src.app.web_routes import router as web_router  # все HTML-страницы
from fastapi import Request
from fastapi.responses import HTMLResponse
from src.app.core.templates import templates, render_i18n, _get_lang, tr, _inject_en_button
from src.app.routes.profile_routes import router as profile_router


# -----------------------------------------------------------------------------


app = FastAPI(title="AssistChat Platform")


# Middleware и сессии
app.middleware("http")(_authflow_trace)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="assistchat_session",
)

# Статика
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Подключаем модули и ресурсы
app.include_router(qr_router)
app.include_router(bot_router)
app.include_router(telegram_router)
app.include_router(zoom_router)
app.include_router(resources_router)
app.include_router(auth_router)
app.include_router(profile_router)
# Подключаем единый файл со всеми веб-страницами
app.include_router(web_router)


# -----------------------------------------------------------------------------


@app.get("/health")
def health():
    """Проверка работоспособности приложения."""
    return {"ok": True}


# -----------------------------------------
# END
# -----------------------------------------
@app.get("/{full_path:path}", response_class=HTMLResponse)
def render_any_html(request: Request, full_path: str = ""):
    path = full_path.strip("/")
    if path == "" or path.endswith("/"):
        path = path + "index"
    if not path.endswith(".html"):
        path = path + ".html"
    if ".." in path or path.startswith("/"):
        return render_i18n("404.html", request, "404", {"error_message": "Извините, такой страницы нет."})

    try:
        rendered = templates.get_template(path).render(request=request)
    except Exception:
        return render_i18n("404.html", request, "404", {"error_message": "Извините, такой страницы нет."})

    lang = _get_lang(request)
    page_key = path[:-5].replace("/", "_")
    translated = tr.translate_html(rendered, target_lang=lang, page_name=page_key)
    return HTMLResponse(content=_inject_en_button(translated, lang))

