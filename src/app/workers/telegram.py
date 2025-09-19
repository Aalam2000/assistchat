# src/app/workers/telegram.py
from telethon import TelegramClient, events
from telethon.sessions import StringSession

from src.app.workers.base import BaseWorker
from src.common.db import SessionLocal
from src.models.message import Message


class TelegramWorker(BaseWorker):
    def __init__(self, resource):
        super().__init__(resource)
        self.client: TelegramClient | None = None

    async def start(self):
        await super().start()

        creds = (self.resource.meta_json or {}).get("creds", {})
        app_id = creds.get("app_id")
        app_hash = creds.get("app_hash")
        string_session = creds.get("string_session")

        if not app_id or not app_hash or not string_session:
            raise ValueError(f"[TG] Resource {self.resource.id} missing credentials")

        self.client = TelegramClient(StringSession(string_session), app_id, app_hash)
        await self.client.connect()

        # 🔹 создаём движок диалогов для этой линии
        from src.app.dialogs.telegram_dialog import TelegramDialogEngine
        self.dialog_engine = TelegramDialogEngine(self.resource)

        # подписка на входящие сообщения
        @self.client.on(events.NewMessage)
        async def handler(event):
            if self.apply_rules(event.message):
                print(f"[TG][{self.resource.id}] MSG from {event.sender_id}: {event.text}")
                self._save_message(event, direction="in")

                # 🔹 вызываем движок для ответа
                reply = self.dialog_engine.handle_message(event)
                if reply:
                    sent = await self.client.send_message(event.sender_id, reply)
                    self._save_message(sent, direction="out")
            else:
                print(f"[TG][{self.resource.id}] Blocked message from {event.sender_id}")

        print(f"[TG] Worker started for resource {self.resource.id}")

    async def stop(self):
        await super().stop()
        if self.client:
            await self.client.disconnect()
            self.client = None
        print(f"[TG] Worker stopped for resource {self.resource.id}")

    def apply_rules(self, message):
        meta = self.resource.meta_json or {}
        lists = meta.get("lists", {})
        whitelist = lists.get("whitelist") or []
        blacklist = lists.get("blacklist") or []

        sender = str(getattr(message, "sender_id", ""))

        if blacklist and sender in blacklist:
            return False
        if whitelist and sender not in whitelist:
            return False
        return True

    def _save_message(self, event, direction: str):
        """Сохраняем входящее/исходящее сообщение в БД"""
        db = SessionLocal()
        try:
            msg = Message(
                resource_id=self.resource.id,
                peer_id=event.sender_id or 0,
                peer_type="group" if event.is_group else "user",
                chat_id=getattr(event.chat, "id", None),
                msg_id=event.id,
                direction=direction,
                msg_type="text",
                text=event.raw_text or "",
                provider="telegram",
                external_chat_id=str(event.chat_id),
                external_msg_id=str(event.id),
            )
            db.add(msg)
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"[TG][{self.resource.id}] save_message error:", e)
        finally:
            db.close()

    async def send_message(self, peer_id: int, text: str):
        """Отправляем сообщение и сохраняем в БД"""
        if not self.client:
            raise RuntimeError("Telegram client not running")

        try:
            sent = await self.client.send_message(peer_id, text)
            self._save_message(sent, direction="out")
            return sent
        except Exception as e:
            print(f"[TG][{self.resource.id}] send_message error:", e)
            raise
