# src/app/resources/telegram/telegram.py
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from telethon import TelegramClient, events
from telethon.sessions import StringSession

from src.app.core.db import SessionLocal
from src.app.core.message_bus import MessageEvent, bus
from src.models.resource import Resource
from src.models.user import User


def _utcnow():
    return datetime.now(timezone.utc)


def _short_text(s: str, limit: int = 500) -> str:
    s = (s or "").strip().replace("\r", "").replace("\n", "\\n")
    return s if len(s) <= limit else (s[:limit] + "…")


class TelegramWorker:
    """
    Telethon user-session воркер.

    Ответственность: подключиться к Telegram, слушать входящие сообщения
    и публиковать их в шину (MessageBus).

    Вся логика правил, фильтрации и AI — в PROMPT-воркере.
    """

    def __init__(self, resource: Resource):
        self.resource = resource
        self.client: TelegramClient | None = None
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._running = False
        self._me_id: int | None = None  # ID собственного аккаунта сессии
        # дедупликация альбомов: grouped_id -> (timestamp, has_text)
        self._seen_groups: dict[int, tuple[float, bool]] = {}

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
        if self.client:
            try:
                await self.client.disconnect()
            except Exception:
                pass
            self.client = None

    def _log(self, msg: str) -> None:
        rid = str(getattr(self.resource, "id", ""))
        label = getattr(self.resource, "label", "") or rid
        print(f"[TG] {label}({rid}) {msg}", flush=True)

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
                creds = (meta.get("creds") or {})
                app_id = creds.get("app_id")
                app_hash = creds.get("app_hash")
                string_session = creds.get("string_session")

                if not app_id or not app_hash or not string_session:
                    await self._set_state(
                        phase="error",
                        code="telegram_creds_missing",
                        message="missing app_id/app_hash/string_session",
                    )
                    self._log("error: missing creds")
                    return
            finally:
                db.close()

            await self._set_state(phase="starting", code=None, message=None)
            self._log("connecting...")

            rid_str = str(self.resource.id)

            try:
                self.client = TelegramClient(
                    StringSession(str(string_session)), int(app_id), str(app_hash)
                )
                await self.client.connect()
                self._log("connected")

                if not await self.client.is_user_authorized():
                    await self._set_state(
                        phase="error",
                        code="telegram_not_authorized",
                        message="string_session not authorized",
                    )
                    self._log("error: NOT authorized")
                    await self.stop()
                    return

                # Запоминаем ID собственного аккаунта — для фильтрации своих сообщений
                try:
                    me = await self.client.get_me()
                    self._me_id = me.id
                    self._log(f"me_id={self._me_id}")
                except Exception:
                    self._me_id = None

                self._running = True
                await self._set_state(phase="running", code=None, message=None)
                self._log("running: authorized; listening NewMessage")

                @self.client.on(events.NewMessage)
                async def on_message(event):
                    if self._stop.is_set():
                        return

                    # не обрабатываем свои исходящие
                    if event.out:
                        return

                    text = (event.raw_text or "").strip()
                    chat_id = getattr(event, "chat_id", None)
                    sender_id = getattr(event, "sender_id", None)
                    msg_id = getattr(getattr(event, "message", None), "id", None)

                    if chat_id is None or msg_id is None:
                        return

                    # Пропускаем сообщения от своего же аккаунта (пересылки в бота и т.п.)
                    if self._me_id and sender_id == self._me_id:
                        return

                    # 1. Определяем тип чата
                    if getattr(event, "is_private", False):
                        peer_type = "private"
                    elif getattr(event, "is_group", False):
                        peer_type = "group"
                    elif getattr(event, "is_channel", False):
                        peer_type = "channel"
                    else:
                        peer_type = "chat"

                    # 2. Получаем отправителя
                    sender_username: str | None = None
                    is_bot = False
                    try:
                        sndr = await event.get_sender()
                        if sndr:
                            uname = getattr(sndr, "username", None)
                            fname = getattr(sndr, "first_name", None)
                            lname = getattr(sndr, "last_name", None)
                            is_bot = bool(getattr(sndr, "bot", False))
                            if uname:
                                sender_username = uname
                            elif fname or lname:
                                sender_username = " ".join(filter(None, [fname, lname]))
                    except Exception:
                        pass

                    # Игнорируем сообщения от ботов — предотвращаем петли
                    if is_bot:
                        return

                    # Дедупликация альбомов: обрабатываем только первое фото,
                    # текст подписи будет получен через download_album.
                    grouped_id = getattr(getattr(event, "message", None), "grouped_id", None)
                    if grouped_id is not None:
                        now = time.monotonic()
                        # чистим устаревшие записи (>60 сек)
                        self._seen_groups = {
                            g: v for g, v in self._seen_groups.items()
                            if now - v[0] < 60
                        }
                        if grouped_id in self._seen_groups:
                            return  # уже обработали первое фото этого альбома
                        self._seen_groups[grouped_id] = (now, False)

                    # 3. Получаем название и @username группы/канала
                    chat_name: str | None = None
                    chat_username: str | None = None
                    try:
                        if peer_type in ("group", "channel"):
                            chat_entity = (
                                getattr(event, "chat", None) or await event.get_chat()
                            )
                            if chat_entity:
                                chat_name = getattr(chat_entity, "title", None)
                                cu = getattr(chat_entity, "username", None)
                                if cu:
                                    chat_username = cu
                    except Exception:
                        pass

                    msg = getattr(event, "message", None)
                    msg_type = "text"
                    if grouped_id is not None:
                        msg_type = "album"  # альбом (несколько фото/видео)
                    elif not text:
                        if getattr(msg, "voice", None) or getattr(msg, "audio", None):
                            msg_type = "voice"
                        elif getattr(msg, "photo", None):
                            msg_type = "photo"
                        elif getattr(msg, "document", None) or getattr(msg, "media", None):
                            msg_type = "file"

                    direction = "OUT" if event.out else "IN"
                    self._log(
                        f"{direction} peer_type={peer_type} chat_id={chat_id} "
                        f"sender_id={sender_id} msg_id={msg_id} "
                        f"type={msg_type} text={_short_text(text)}"
                    )

                    evt = MessageEvent(
                        source_type="telegram_session",
                        source_rid=rid_str,
                        peer_id=int(sender_id or 0),
                        peer_type=peer_type,
                        chat_id=int(chat_id),
                        sender_username=sender_username,
                        chat_username=chat_username,
                        msg_id=int(msg_id),
                        external_chat_id=str(chat_id),
                        external_msg_id=str(msg_id),
                        text=text,
                        msg_type=msg_type,
                        source_label=self.resource.label,
                        chat_name=chat_name,
                        raw={
                            "event_type": "new_message",
                            "grouped_id": grouped_id,
                        },
                    )

                    await bus.publish(rid_str, evt)

                await self.client.run_until_disconnected()

            except asyncio.CancelledError:
                return
            except Exception as e:
                self._running = False
                try:
                    from telethon.errors import FloodWaitError as _FWE
                    if isinstance(e, _FWE):
                        wait_sec = max(int(getattr(e, "seconds", 60)), 60)
                        await self._set_state(
                            phase="error",
                            code="telegram_flood_wait",
                            message=f"FloodWait {wait_sec}s",
                        )
                        self._log(f"FloodWait: sleeping {wait_sec}s")
                        await asyncio.sleep(wait_sec)
                    else:
                        await self._set_state(
                            phase="error",
                            code="telegram_runtime_error",
                            message=str(e),
                        )
                        self._log(f"runtime_error: {e!r}")
                        await asyncio.sleep(5)
                except Exception:
                    await asyncio.sleep(5)
            finally:
                self._running = False
                if self.client:
                    try:
                        await self.client.disconnect()
                    except Exception:
                        pass
                    self.client = None

            await asyncio.sleep(1)


    async def download_album(
        self,
        from_chat_id: int,
        msg_id: int,
        grouped_id: int | None = None,
    ) -> tuple[list[bytes], str]:
        """Скачать все фото альбома. Возвращает (байты фото, текст подписи)."""
        if not self.client:
            return [], ""
        try:
            if grouped_id:
                nearby = await self.client.get_messages(
                    entity=from_chat_id,
                    min_id=max(1, msg_id - 15),
                    max_id=msg_id + 15,
                    limit=20,
                )
                album_msgs = sorted(
                    [m for m in nearby if m and getattr(m, "grouped_id", None) == grouped_id],
                    key=lambda m: m.id,
                )
            else:
                msgs = await self.client.get_messages(entity=from_chat_id, ids=[msg_id])
                album_msgs = [m for m in (msgs or []) if m]

            results: list[bytes] = []
            caption = ""
            for msg in album_msgs:
                # Текст подписи — берём из первого сообщения где он есть
                if not caption:
                    caption = (getattr(msg, "message", None) or "").strip()
                if getattr(msg, "photo", None) or getattr(msg, "document", None):
                    data = await self.client.download_media(msg, bytes)
                    if data:
                        results.append(data)
            self._log(f"download_album grouped_id={grouped_id} → {len(results)} files")
            return results, caption
        except Exception as e:
            self._log(f"download_album error: {e!r}")
            return [], ""

    async def forward_message(self, to_peer: int, from_chat_id: int, msg_id: int) -> bool:
        """Переслать оригинальное сообщение (с медиа) через Telethon."""
        if not self.client:
            return False
        try:
            await self.client.forward_messages(
                entity=to_peer,
                messages=[msg_id],
                from_peer=from_chat_id,
            )
            return True
        except Exception as e:
            self._log(f"forward_message error: {e!r}")
            return False


class SessionRegistry:
    def __init__(self):
        self._workers: dict[str, TelegramWorker] = {}
        self._lock = asyncio.Lock()

    async def ensure_started(self, resource: Resource) -> TelegramWorker:
        from src.app.modules.bot.guard import require_resource_bot_active

        require_resource_bot_active(resource)
        async with self._lock:
            rid = str(resource.id)
            w = self._workers.get(rid)
            if not w:
                w = TelegramWorker(resource)
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

    def get(self, resource_id: str) -> TelegramWorker | None:
        return self._workers.get(str(resource_id))

    def status(self) -> dict[str, str]:
        return {rid: "telegram" for rid, w in self._workers.items() if w.is_running}


session_registry = SessionRegistry()
