"""
Главный модуль приложения AssistChat.
Назначение: собрать FastAPI-приложение, подключив ядро, модули и ресурсы.
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

# ядро
from src.app.core.middleware import _authflow_trace
from src.app.core.config import BASE_DIR, SESSION_SECRET

# вынесенные маршруты
from src.app.routes.auth_routes import router as auth_router
from src.app.routes.profile_routes import router as profile_router
from src.app.modules.qr.router import router as qr_router
from src.app.modules.bot.router import router as bot_router
from src.app.resources.telegram.router import router as telegram_router
from src.app.resources.zoom.router import router as zoom_router

# legacy fallback (остальные старые маршруты)
from src.app import main_legacy


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
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Подключаем модули и ресурсы
app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(qr_router)
app.include_router(bot_router)
app.include_router(telegram_router)
app.include_router(zoom_router)

# Подключаем все оставшиеся маршруты из main_legacy
app.mount("", main_legacy.app)

# -----------------------------------------------------------------------------

@app.get("/health")
def health():
    """Проверка работоспособности приложения."""
    return {"ok": True}
