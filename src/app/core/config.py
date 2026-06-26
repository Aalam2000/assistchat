"""
src/app/core/config.py — базовые параметры конфигурации приложения.
"""

import os
from pathlib import Path
from passlib.context import CryptContext

# Корневая директория приложения
BASE_DIR = Path(__file__).resolve().parents[2]  # src/
WEB_DIR = BASE_DIR / "web"
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

# Директория для хранения пользовательских файлов (аудио, отчёты, пр.)
BASE_STORAGE = BASE_DIR.parent / "storage"
BASE_STORAGE.mkdir(parents=True, exist_ok=True)

# Секрет для cookie-сессий (можно переопределить через .env)
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret-change-me")

# Контекст шифрования паролей
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# -----------------------------------------------------------------------------
# Настройка подключения к PostgreSQL (используется Alembic и FastAPI)
# -----------------------------------------------------------------------------
from src.app.core import db

SQLALCHEMY_DATABASE_URL = db.DATABASE_URL

# -----------------------------------------------------------------------------
# i18n (auto-i18n-lib)
# -----------------------------------------------------------------------------
PROJECT_ROOT = BASE_DIR.parent
TRANSLATIONS_DIR = PROJECT_ROOT / "translations"

SOURCE_LANG = os.getenv("SOURCE_LANG", "ru")
AUTO_I18N_TARGET_LANGS = [
    item.strip()
    for item in os.getenv("AUTO_I18N_TARGET_LANGS", "en").split(",")
    if item.strip()
]
