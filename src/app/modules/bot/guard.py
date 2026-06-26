"""
Обёртка bot_enabled: единая проверка перед запуском любого воркера.
"""
from __future__ import annotations

from sqlalchemy import text

from src.app.core.db import SessionLocal

_WORKER_PROVIDERS = ("telegram", "telegram_bot", "prompt", "chat_base")


class BotInactive(Exception):
    """У пользователя выключен глобальный переключатель bot_enabled."""

    def __init__(self, user_id: int | None = None):
        self.user_id = user_id
        super().__init__(f"bot inactive for user_id={user_id}")


def is_bot_active(user_id: int | None, db=None) -> bool:
    if not user_id:
        return False
    own_db = db is None
    if own_db:
        db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT bot_enabled FROM users WHERE id = :uid"),
            {"uid": user_id},
        ).first()
        return bool(row and row[0])
    finally:
        if own_db:
            db.close()


def require_bot_active(user_id: int | None, db=None) -> None:
    if not is_bot_active(user_id, db):
        raise BotInactive(user_id)


def require_resource_bot_active(resource, db=None) -> None:
    require_bot_active(getattr(resource, "user_id", None), db)


def is_resource_bot_active(resource, db=None) -> bool:
    return is_bot_active(getattr(resource, "user_id", None), db)


def stop_user_background_tasks(user_id: int) -> dict:
    """Останавливает фоновые задачи web-процесса (chat_base и т.п.)."""
    from src.app.resources.chat_base.run_control import (
        is_running,
        request_stop,
    )
    from src.models.resource import Resource

    stopped: list[str] = []
    db = SessionLocal()
    try:
        rows = (
            db.query(Resource)
            .filter(
                Resource.user_id == user_id,
                Resource.provider == "chat_base",
            )
            .all()
        )
        for row in rows:
            rid = str(row.id)
            if is_running(rid) and request_stop(rid):
                stopped.append(rid)
    finally:
        db.close()
    return {"stopped_chat_base": stopped}


def count_running_resources(user_id: int, db) -> int:
    from src.app.resources.chat_base.run_control import (
        is_running as cb_is_running,
    )
    from src.models.resource import Resource

    rows = (
        db.query(Resource)
        .filter(
            Resource.user_id == user_id,
            Resource.provider.in_(_WORKER_PROVIDERS),
        )
        .all()
    )
    count = 0
    for row in rows:
        if row.provider == "chat_base":
            if cb_is_running(str(row.id)):
                count += 1
        elif row.status == "active" and row.phase in ("running", "starting"):
            count += 1
    return count
