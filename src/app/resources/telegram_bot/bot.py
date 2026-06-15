# src/app/resources/telegram_bot/bot.py
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ContentType, ParseMode
from aiogram.filters import Command

from src.app.core.db import SessionLocal
from src.app.core.message_bus import MessageEvent, bus
from src.models.resource import Resource
from src.models.user import User


def _utcnow():
    return datetime.now(timezone.utc)


def _short_text(s: str, limit: int = 300) -> str:
    s = (s or "").strip()
    return s if len(s) <= limit else (s[:limit] + "…")


class TelegramBotWorker:
    """
    Aiogram bot воркер.

    Ответственность: подключить бота, слушать входящие сообщения,
    публиковать их в MessageBus.

    Вся логика правил, фильтрации и AI — в PROMPT-воркере.
    """

    def __init__(self, resource: Resource):
        self.resource = resource
        self.bot: Bot | None = None
        self.dp: Dispatcher | None = None
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def update_resource(self, resource: Resource) -> None:
        self.resource = resource

    def launch(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self.start())

    async def stop(self) -> None:
        self._stop.set()
        self._running = False
        if self.bot:
            try:
                await self.bot.session.close()
            except Exception:
                pass
            self.bot = None
        self.dp = None

    def _log(self, msg: str) -> None:
        rid = str(getattr(self.resource, "id", ""))
        label = getattr(self.resource, "label", "") or rid
        print(f"[TG_BOT] {label}({rid}) {msg}", flush=True)

    async def _set_state(self, *, phase: str, code: str | None = None, message: str | None = None) -> None:
        db = SessionLocal()
        try:
            r = db.get(Resource, self.resource.id)
            if not r:
                return
            r.phase = phase
            r.last_checked_at = _utcnow()
            r.last_error_code = code
            r.error_message = message
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    async def send_message(self, chat_id: int | str, text: str, parse_mode: str | None = None) -> bool:
        """Отправить сообщение. Вызывается из PROMPT-воркера."""
        if not self.bot:
            self._log(f"send_message: bot not running, chat_id={chat_id}")
            return False
        try:
            await self.bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
            return True
        except Exception as e:
            self._log(f"send_message error: {e!r}")
            return False

    async def send_media_group(
        self,
        chat_id: int | str,
        photos: list[bytes],
        caption: str = "",
    ) -> bool:
        """Отправить несколько фото как альбом через Bot API."""
        if not self.bot or not photos:
            return False
        try:
            from aiogram.types import BufferedInputFile, InputMediaPhoto
            items = []
            for i, data in enumerate(photos):
                items.append(InputMediaPhoto(
                    media=BufferedInputFile(data, filename=f"photo_{i}.jpg"),
                    caption=caption if i == 0 else None,
                ))
            await self.bot.send_media_group(chat_id=chat_id, media=items)
            return True
        except Exception as e:
            self._log(f"send_media_group error: {e!r}")
            return False

    async def start(self) -> None:
        self._log("start() entered")

        while not self._stop.is_set():
            db = SessionLocal()
            try:
                r = db.get(Resource, self.resource.id)
                if not r:
                    self._log("resource not found in DB -> stop")
                    return
                u = db.get(User, r.user_id) if r.user_id else None

                if not u or not getattr(u, "bot_enabled", False):
                    await self._set_state(phase="paused")
                    self._log("paused: user.bot_enabled is false")
                    return

                if r.status != "active":
                    await self._set_state(phase="paused")
                    self._log(f"paused: resource status={r.status!r}")
                    return

                meta = r.meta_json or {}
                creds = meta.get("creds") or {}
                bot_token = (creds.get("bot_token") or "").strip()

                if not bot_token:
                    await self._set_state(
                        phase="error",
                        code="telegram_bot_token_missing",
                        message="missing bot_token",
                    )
                    self._log("error: missing bot_token")
                    return
            finally:
                db.close()

            await self._set_state(phase="starting", code=None, message=None)
            self._log("connecting...")

            rid_str = str(self.resource.id)

            try:
                self.bot = Bot(
                    token=bot_token,
                    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
                )
                self.dp = Dispatcher()

                @self.dp.message()
                async def on_message(message: types.Message) -> None:
                    if self._stop.is_set():
                        return

                    # Пересланные сообщения — не обрабатываем (пользователь сам переслал что-то в бота)
                    if getattr(message, "forward_origin", None) or getattr(message, "forward_from", None) or getattr(message, "forward_from_chat", None):
                        return

                    chat = message.chat
                    sender = message.from_user

                    chat_id = chat.id
                    peer_id = sender.id if sender else 0
                    sender_username = sender.username if sender else None

                    text = (message.text or message.caption or "").strip()

                    if chat.type == "private":
                        peer_type = "private"
                    elif chat.type in ("group", "supergroup"):
                        peer_type = "group"
                    elif chat.type == "channel":
                        peer_type = "channel"
                    else:
                        peer_type = "chat"

                    msg_type = "text"
                    if message.content_type == ContentType.VOICE:
                        msg_type = "voice"
                    elif message.content_type == ContentType.AUDIO:
                        msg_type = "voice"
                    elif message.content_type == ContentType.DOCUMENT:
                        msg_type = "file"
                    elif message.content_type == ContentType.PHOTO:
                        msg_type = "image"

                    self._log(
                        f"IN peer_type={peer_type} chat_id={chat_id} "
                        f"sender_id={peer_id} msg_id={message.message_id} "
                        f"type={msg_type} text={_short_text(text)}"
                    )

                    evt = MessageEvent(
                        source_type="telegram_bot",
                        source_rid=rid_str,
                        peer_id=peer_id,
                        peer_type=peer_type,
                        chat_id=chat_id,
                        sender_username=sender_username,
                        msg_id=message.message_id,
                        external_chat_id=str(chat_id),
                        external_msg_id=str(message.message_id),
                        text=text,
                        msg_type=msg_type,
                        raw={"content_type": message.content_type},
                    )
                    await bus.publish(rid_str, evt)

                # Проверяем токен (getMe)
                me = await self.bot.get_me()
                self._log(f"authorized as @{me.username} (id={me.id})")

                self._running = True
                await self._set_state(phase="running", code=None, message=None)
                self._log("running: polling started")

                await self.dp.start_polling(
                    self.bot,
                    handle_signals=False,
                    allowed_updates=["message", "edited_message"],
                )

            except asyncio.CancelledError:
                return
            except Exception as e:
                self._running = False
                await self._set_state(
                    phase="error",
                    code="telegram_bot_runtime_error",
                    message=str(e),
                )
                self._log(f"runtime_error: {e!r}")
                await asyncio.sleep(5)
            finally:
                self._running = False
                if self.bot:
                    try:
                        await self.bot.session.close()
                    except Exception:
                        pass
                    self.bot = None
                self.dp = None

            await asyncio.sleep(1)


class BotRegistry:
    def __init__(self):
        self._workers: dict[str, TelegramBotWorker] = {}
        self._lock = asyncio.Lock()

    async def ensure_started(self, resource: Resource) -> TelegramBotWorker:
        async with self._lock:
            rid = str(resource.id)
            w = self._workers.get(rid)
            if not w:
                w = TelegramBotWorker(resource)
                self._workers[rid] = w
            else:
                w.update_resource(resource)
            w.launch()
            return w

    async def stop(self, resource_id: str) -> None:
        async with self._lock:
            w = self._workers.pop(str(resource_id), None)
        if w:
            await w.stop()

    def get(self, resource_id: str) -> TelegramBotWorker | None:
        return self._workers.get(str(resource_id))

    def status(self) -> dict[str, str]:
        return {rid: "telegram_bot" for rid, w in self._workers.items() if w.is_running}


bot_registry = BotRegistry()
