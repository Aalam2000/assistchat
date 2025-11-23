"""
src/app/resources/telegram/telegram_dialog.py
─────────────────────────────────────────────────────────────────────────────
TelegramDialogEngine — модуль диалоговой логики ресурса Telegram.

Назначение:
    • Управляет логикой общения Telegram-агента с пользователями и группами;
    • Загружает историю диалогов и применяет промпты;
    • Делает запросы к OpenAI (через OpenAIClient);
    • Возвращает ответ и данные по использованию токенов.

Особенности новой архитектуры:
    • Полностью сохранён старый функционал;
    • Поддержка контекстной памяти и голосовых ответов;
    • Безопасная обработка ошибок и fallback при сбоях OpenAI;
    • Совместимость с новой системой SessionRegistry и BotManager.
"""

from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime, timezone

from src.models.message import Message
from src.models.resource import Resource
from src.models.user import User
from src.app.core.db import SessionLocal
from src.app.resources.telegram.openai_client import OpenAIClient, get_api_key


class TelegramDialogEngine:
    """Управляет логикой диалога для одного Telegram-ресурса."""

    def __init__(self, resource: Resource):
        self.resource = resource
        self.db: Session = SessionLocal()

        # Определяем владельца ресурса
        self.user: User | None = self.db.get(User, resource.user_id)

        # Определяем, использовать ли пользовательский ключ
        user_key = getattr(self.user, "openai_api_key", None)
        profile_flags = getattr(self.user, "meta_json", {}) or {}
        use_custom = bool(profile_flags.get("use_custom_key") and user_key)

        # Инициализация клиента OpenAI
        api_key = user_key if use_custom else get_api_key(self.user)
        self.openai_client = OpenAIClient(self.user, api_key_override=api_key)

    # ────────────────────────────────────────────────────────────────
    async def handle_message(
        self,
        event,
        audio_bytes: bytes | None = None,
        prefer_voice_reply: bool = False
    ) -> dict | None:
        """
        Асинхронная обработка входящего сообщения Telegram.
        Возвращает структуру:
        {
            "text": str,
            "tokens": int,
            "audio_bytes": bytes|None,
            "mode": "text"|"voice"
        }
        """
        text = (event.raw_text or "").strip()

        # ─── Распознавание аудио, если нет текста ─────────────────────────────
        if audio_bytes and not text:
            try:
                text = await self.openai_client.transcribe_audio(audio_bytes)
                print(f"[TG_DIALOG][{self.resource.id}] Распознан текст: {text}")
            except Exception as e:
                print(f"[TG_DIALOG][{self.resource.id}] Ошибка распознавания аудио: {e}")
                text = ""

        if not text:
            return None

        # ─── Формирование контекста ──────────────────────────────────────────
        limit = (self.resource.meta_json or {}).get("limits", {}).get("history_length", 20)
        peer_id = getattr(event, "chat_id", None) or getattr(event, "sender_id", None)
        context_rows = self.get_context(self.db, peer_id=peer_id, limit=limit)

        # Фильтрация и анти-зацикливание
        context = []
        for m in context_rows:
            if not m.text:
                continue
            role = "user" if m.direction == "in" else "assistant"
            # убираем дубликаты сообщений
            if len(context) > 0 and context[-1]["content"] == m.text:
                continue
            context.append({"role": role, "content": m.text})

        # ─── Системный промпт ────────────────────────────────────────────────
        prompts = (self.resource.meta_json or {}).get("prompts", {})
        system_prompt = "\n".join(
            filter(None, [
                (prompts.get("settings") or "").strip(),
                (prompts.get("rules_common") or "").strip(),
                (prompts.get("rules_dialog") or "").strip(),
            ])
        ).strip()

        # ─── Вызов OpenAI ───────────────────────────────────────────────────
        try:
            reply = await self.openai_client.handle_message(
                text=text,
                audio_bytes=audio_bytes,
                system_prompt=system_prompt,
                context=context,
                prefer_voice_reply=prefer_voice_reply,
            )
        except Exception as e:
            print(f"[TG_DIALOG][{self.resource.id}] OpenAI error: {e}")
            return {
                "text": f"⚠️ Ошибка при обращении к OpenAI: {e}",
                "tokens": 0,
                "audio_bytes": None,
                "mode": "text",
            }

        # ─── Защита и нормализация ответа ────────────────────────────────────
        reply = reply or {}
        reply.setdefault("text", "")
        reply.setdefault("tokens", 0)
        reply.setdefault("audio_bytes", None)
        reply.setdefault("mode", "voice" if prefer_voice_reply and reply.get("audio_bytes") else "text")

        # ─── Фиксируем последнюю активность ресурса ─────────────────────────
        try:
            r = self.db.get(Resource, self.resource.id)
            if r:
                r.last_activity = datetime.now(timezone.utc)
                r.usage_today = (r.usage_today or 0) + int(reply.get("tokens") or 0)
                self.db.commit()
        except Exception as e:
            print(f"[TG_DIALOG][{self.resource.id}] update resource activity error:", e)
            self.db.rollback()

        return reply

    # ────────────────────────────────────────────────────────────────
    def get_context(self, db: Session, peer_id: int, limit: int | None = None):
        """Загружает последние N сообщений с данным собеседником."""
        try:
            meta = (self.resource.meta_json or {})
            history_limit = int(limit or meta.get("history_limit") or 20)

            rows = db.execute(
                select(Message)
                .where(
                    Message.resource_id == self.resource.id,
                    Message.peer_id == peer_id,
                )
                .order_by(Message.created_at.desc())
                .limit(history_limit)
            ).scalars().all()

            return list(reversed(rows))
        except Exception as e:
            print(f"[TG_DIALOG][{self.resource.id}] get_context error:", e)
            return []

    # ────────────────────────────────────────────────────────────────
    def apply_prompts(self, text: str) -> str:
        """Локальная обработка без OpenAI — fallback при сбоях."""
        prompts = (self.resource.meta_json or {}).get("prompts", {})
        rules_common = (prompts.get("rules_common") or "").strip()
        rules_dialog = (prompts.get("rules_dialog") or "").strip()

        reply_parts = []
        if rules_common:
            reply_parts.append(rules_common)
        if rules_dialog:
            reply_parts.append(rules_dialog)
        reply_parts.append(f"Вы сказали: {text}")

        return "\n\n".join(reply_parts)
