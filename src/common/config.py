# src/common/config.py
import os
from dotenv import load_dotenv, find_dotenv

# 1) Пытаемся найти .env поблизости (локальная разработка в PyCharm).
# 2) Если файла нет — не страшно: переменные должны прийти из окружения контейнера.
load_dotenv(find_dotenv(usecwd=True), override=False)

ENV = os.getenv("ENV", "dev")

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

# Не фиксируем путь к .env и не подменяем host/port:
# в докере это придёт из env/compose; локально — из .env, найденного выше.
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

# Psycopg v3 ("psycopg") — как у тебя и было
DATABASE_URL = f"postgresql+psycopg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
