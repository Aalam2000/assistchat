# src/app/dialogs/telegram_dialog.py
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime, timezone

from src.models.message import Message
from src.models.resource import Resource
from src.common.db import SessionLocal

class TelegramDialogEngine:
    """
    Управляет логикой диалога для одного ресурса (линии Telegram).
    """

    def __init__(self, resource: Resource):
        self.resource = resource

    def get_context(self, db: Session, peer_id: int, limit: int = 20):
        """
        Загружает последние N сообщений для конкретного собеседника.
        """
        rows = db.execute(
            select(Message)
            .where(
                Message.resource_id == self.resource.id,
                Message.peer_id == peer_id,
            )
            .order_by(Message.created_at.desc())
            .limit(limit)
        ).scalars().all()
        # возвращаем в обратном порядке (старые → новые)
        return list(reversed(rows))

    def apply_prompts(self, text: str) -> str:
        """
        Применяет правила из meta_json.prompts.
        Сейчас упрощённо: добавляем преамбулу из rules_common.
        """
        prompts = (self.resource.meta_json or {}).get("prompts", {})
        rules_common = (prompts.get("rules_common") or "").strip()
        rules_dialog = (prompts.get("rules_dialog") or "").strip()

        # простая схема: правила + echo-ответ
        reply = ""
        if rules_common:
            reply += f"{rules_common}\n\n"
        if rules_dialog:
            reply += f"{rules_dialog}\n\n"
        reply += f"Вы сказали: {text}"
        return reply

    def handle_message(self, event) -> str | None:
        """
        Обрабатывает входящее сообщение.
        Возвращает текст ответа (или None, если не нужно отвечать).
        """
        text = (event.raw_text or "").strip()
        if not text:
            return None

        # подключение к БД для загрузки контекста
        db = SessionLocal()
        try:
            context = self.get_context(db, peer_id=event.sender_id)
            # (пока не используем, но можно анализировать последние N сообщений)
        finally:
            db.close()

        # пока просто генерим автоответ через prompts
        return self.apply_prompts(text)
