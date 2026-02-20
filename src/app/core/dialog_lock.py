"""
src/app/core/dialog_lock.py
─────────────────────────────────────────────────────────────────────────────
Гарантия строгой последовательности: 1 диалог = 1 обработчик одновременно.

Реализация: PostgreSQL advisory lock по dialog_id.
Лок держится на уровне соединения, поэтому DB-сессия должна жить весь runtime.
"""

from __future__ import annotations

from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def _uuid_to_bigint(dialog_id: UUID) -> int:
    """
    Преобразует UUID -> int64 (signed) для pg_advisory_lock(bigint).
    Коллизии теоретически возможны, но на практике крайне маловероятны.
    """
    b = dialog_id.bytes[:8]
    return int.from_bytes(b, byteorder="big", signed=True)


def acquire_dialog_lock(db: Session, dialog_id: UUID) -> None:
    """
    Блокируется до получения лока.
    """
    key = _uuid_to_bigint(dialog_id)
    db.execute(text("SELECT pg_advisory_lock(:k)"), {"k": key})


def release_dialog_lock(db: Session, dialog_id: UUID) -> None:
    """
    Освобождает лок (если он удерживается этим соединением).
    """
    key = _uuid_to_bigint(dialog_id)
    db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})


@contextmanager
def dialog_lock(db: Session, dialog_id: UUID):
    """
    Контекстный менеджер advisory-lock.
    """
    acquire_dialog_lock(db, dialog_id)
    try:
        yield
    finally:
        try:
            release_dialog_lock(db, dialog_id)
        except Exception:
            # если соединение уже умерло — ок, лок и так будет сброшен
            pass
