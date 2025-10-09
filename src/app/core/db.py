"""
core/db.py — подключение к базе данных и функции для работы с сессиями SQLAlchemy.
"""

from src.common.db import SessionLocal, engine  # используем уже существующую реализацию
from sqlalchemy.orm import Session

def get_db():
    """
    Создаёт и возвращает сессию БД.
    Гарантирует закрытие соединения после использования (через yield).
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
