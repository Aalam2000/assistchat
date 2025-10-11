"""
src/app/core/db.py — подключение к базе данных PostgreSQL.
Содержит движок SQLAlchemy, сессию и базовый класс моделей.
"""

import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# -----------------------------------------------------------------------------
# Конфигурация подключения
# -----------------------------------------------------------------------------

DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "assistchat")
DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = os.getenv("DB_PORT", "5432")

# psycopg (v3) — современный драйвер, совместимый с SQLAlchemy 2.0
DATABASE_URL = f"postgresql+psycopg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# -----------------------------------------------------------------------------
# Инициализация движка и сессии
# -----------------------------------------------------------------------------

engine = create_engine(DATABASE_URL, echo=False, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


# -----------------------------------------------------------------------------
# Базовый класс для ORM-моделей
# -----------------------------------------------------------------------------
class Base(DeclarativeBase):
    """Базовый класс для всех моделей SQLAlchemy."""
    pass


# -----------------------------------------------------------------------------
# Утилита проверки подключения (по желанию)
# -----------------------------------------------------------------------------
def check_db() -> str:
    """Возвращает версию PostgreSQL — для тестов подключения."""
    with engine.connect() as conn:
        return conn.execute(text("select version();")).scalar_one()


# -----------------------------------------------------------------------------
# Dependency FastAPI
# -----------------------------------------------------------------------------
def get_db():
    """FastAPI dependency для предоставления сессии БД."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
