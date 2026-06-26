"""
src/app/core/config.py — базовые параметры конфигурации приложения.
Содержит пути, секреты и глобальные константы, используемые во всех модулях.
"""

import json
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

_DEFAULT_I18N_LANG_LABELS = {
    "ru": "Русский",
    "en": "English",
    "az": "Azərbaycan",
    "tr": "Türkçe",
}


def get_i18n_lang_labels() -> dict[str, str]:
    raw = os.getenv("AUTO_I18N_LANG_LABELS", "").strip()
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return {str(k).lower(): str(v) for k, v in data.items()}
        except json.JSONDecodeError:
            pass
    return dict(_DEFAULT_I18N_LANG_LABELS)
