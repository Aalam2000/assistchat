# src/app/resources/telegram/telegram.py
from __future__ import annotations

import asyncio
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

                    sender_username: str | None = None
                    try:
                        sndr = await event.get_sender()
                        if sndr:
                            sender_username = getattr(sndr, "username", None)
                    except Exception:
                        pass

                    if getattr(event, "is_private", False):
                        peer_type = "private"
                    elif getattr(event, "is_group", False):
                        peer_type = "group"
                    elif getattr(event, "is_channel", False):
                        peer_type = "channel"
                    else:
                        peer_type = "chat"

                    msg_type = "text"
                    if not text:
                        msg = getattr(event, "message", None)
                        if getattr(msg, "voice", None) or getattr(msg, "audio", None):
                            msg_type = "voice"
                        elif getattr(msg, "document", None) or getattr(msg, "media", None):
                            msg_type = "file"
                        elif getattr(msg, "photo", None):
                            msg_type = "image"

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
                        msg_id=int(msg_id),
                        external_chat_id=str(chat_id),
                        external_msg_id=str(msg_id),
                        text=text,
                        msg_type=msg_type,
                        raw={"event_type": "new_message"},
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


class SessionRegistry:
    def __init__(self):
        self._workers: dict[str, TelegramWorker] = {}
        self._lock = asyncio.Lock()

    async def ensure_started(self, resource: Resource) -> TelegramWorker:
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

    def status(self) -> dict[str, str]:
        return {rid: "telegram" for rid, w in self._workers.items() if w.is_running}


session_registry = SessionRegistry()
