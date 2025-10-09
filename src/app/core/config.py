"""
core/config.py — базовые параметры конфигурации приложения.
Содержит пути, секреты и глобальные константы, используемые во всех модулях.
"""

import os
from pathlib import Path
from passlib.context import CryptContext

# Корневая директория приложения
BASE_DIR = Path(__file__).resolve().parent.parent

# Директория для хранения пользовательских файлов (аудио, отчёты, пр.)
BASE_STORAGE = BASE_DIR.parent / "storage"
BASE_STORAGE.mkdir(parents=True, exist_ok=True)

# Секрет для cookie-сессий (можно переопределить через .env)
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret-change-me")

# Контекст шифрования паролей
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
