"""
src/app/main.py — главный модуль AssistChat (обновлён под модульную архитектуру)
"""

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from starlette.middleware.sessions import SessionMiddleware

from src.app.core.config import BASE_DIR, SESSION_SECRET, STATIC_DIR
from src.app.core.middleware import _authflow_trace
from src.app.modules.bot.router import router as bot_router
from src.app.modules.qr.router import router as qr_router
from src.app.routes.auth_routes import router as auth_router
from src.app.routes.profile_routes import router as profile_router
from src.app.web_routes import router as web_router

from src.app.core.templates import templates, render_i18n, _get_lang, tr, _inject_en_button
from src.app import providers


# -----------------------------------------------------------------------------
app = FastAPI(title="AssistChat Platform")

# Middleware и сессии
app.middleware("http")(_authflow_trace)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, session_cookie="assistchat_session")

# Подключаем статику
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ─────────────────────────────────────────────────────────────────────────────
# Подключаем базовые модули
# ─────────────────────────────────────────────────────────────────────────────
app.include_router(qr_router)
app.include_router(bot_router)
app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(web_router)
providers.load_all_providers()
app.include_router(providers.router)

# ─────────────────────────────────────────────────────────────────────────────
# Автоподключение всех провайдеров (Telegram, Zoom и т.д.)
# ─────────────────────────────────────────────────────────────────────────────

for name in providers.PROVIDERS.keys():
    try:
        module = __import__(f"src.app.resources.{name}", fromlist=["router"])
        router = getattr(module, "router", None)
        if router:
            app.include_router(router)
            print(f"[MAIN] ✅ Подключён router провайдера: {name}")
        else:
            print(f"[MAIN] ⚠️ Провайдер {name} без router.py — пропущен")
    except Exception as e:
        print(f"[MAIN] ⚠️ Ошибка подключения провайдера {name}: {e}")

# -----------------------------------------------------------------------------
@app.get("/health")
def health():
    """Проверка работоспособности приложения."""
    return {"ok": True}

# -----------------------------------------------------------------------------
@app.get("/{full_path:path}", response_class=HTMLResponse)
def render_any_html(request: Request, full_path: str = ""):
    """Рендер статических HTML-страниц с переводом."""
    path = full_path.strip("/")
    if path == "" or path.endswith("/"):
        path += "index"
    if not path.endswith(".html"):
        path += ".html"
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
