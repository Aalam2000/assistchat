# src/app/resources/telegram/telegram.py
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from telethon import TelegramClient, events
from telethon.sessions import StringSession

from src.app.core.db import SessionLocal
from src.app.core.dialog_service import attach_outgoing_ids, process_incoming
from src.models.resource import Resource
from src.models.user import User


def _utcnow():
    return datetime.now(timezone.utc)


def _short_text(s: str, limit: int = 500) -> str:
    s = (s or "").strip().replace("\r", "").replace("\n", "\\n")
    return s if len(s) <= limit else (s[:limit] + "…")


class TelegramWorker:
    """
    Воркер Telethon (user-session).

    Логи:
      - IN/OUT в консоль botworker.

    Health в Resource:
      - phase: starting/running/paused/error
      - last_error_code/error_message/last_checked_at
    """

    def __init__(self, resource: Resource):
        self.resource = resource
        self.client: TelegramClient | None = None

        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._running = False

        # snapshot правил на момент старта сессии (можно менять через рестарт воркера)
        self._rules: dict = {}

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def update_resource(self, resource: Resource) -> None:
        # важно: если мета/креды поменялись — воркер должен увидеть (через рестарт)
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

    def _allowed_by_rules(self, event) -> bool:
        rules = self._rules or {}
        # defaults: private=True, groups=False, channels=False (как в create)
        reply_private = bool(rules.get("reply_private", True))
        reply_groups = bool(rules.get("reply_groups", False))
        reply_channels = bool(rules.get("reply_channels", False))

        if getattr(event, "is_private", False):
            return reply_private
        if getattr(event, "is_group", False):
            return reply_groups
        if getattr(event, "is_channel", False):
            return reply_channels
        # неизвестный тип чата — безопасно не отвечаем
        return False

    async def start(self) -> None:
        self._log("start() entered")

        while not self._stop.is_set():
            # 1) всегда читаем актуальный ресурс и юзера из БД
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
                creds = (meta.get("creds") or {}) or {}
                app_id = creds.get("app_id")
                app_hash = creds.get("app_hash")
                string_session = creds.get("string_session")

                # snapshot rules на момент запуска
                self._rules = (meta.get("rules") or {}) if isinstance(meta.get("rules"), dict) else {}

                if not app_id or not app_hash or not string_session:
                    await self._set_state(
                        phase="error",
                        code="telegram_creds_missing",
                        message="missing app_id/app_hash/string_session",
                    )
                    self._log("error: missing creds app_id/app_hash/string_session")
                    return
            finally:
                db.close()

            await self._set_state(phase="starting", code=None, message=None)
            self._log("connecting...")

            try:
                self.client = TelegramClient(StringSession(str(string_session)), int(app_id), str(app_hash))
                await self.client.connect()
                self._log("connected")

                if not await self.client.is_user_authorized():
                    await self._set_state(
                        phase="error",
                        code="telegram_not_authorized",
                        message="string_session not authorized",
                    )
                    self._log("error: NOT authorized (string_session)")
                    await self.stop()
                    return

                self._running = True
                await self._set_state(phase="running", code=None, message=None)
                self._log("running: authorized; listening NewMessage")

                @self.client.on(events.NewMessage)
                async def on_message(event):
                    if self._stop.is_set():
                        return

                    direction = "OUT" if event.out else "IN"
                    chat_id = getattr(event, "chat_id", None)
                    sender_id = getattr(event, "sender_id", None)
                    msg_id = getattr(getattr(event, "message", None), "id", None)

                    text = (event.raw_text or "").strip()
                    if text:
                        self._log(
                            f"{direction} chat_id={chat_id} sender_id={sender_id} msg_id={msg_id} "
                            f"text={_short_text(text)}"
                        )
                    else:
                        self._log(f"{direction} chat_id={chat_id} sender_id={sender_id} msg_id={msg_id} <non-text>")

                    # не отвечаем на свои исходящие (анти-цикл)
                    if event.out:
                        return
                    if not text:
                        return
                    if chat_id is None or msg_id is None:
                        return
                    if not self._allowed_by_rules(event):
                        return

                    try:
                        res = await process_incoming(
                            resource_id=self.resource.id,
                            provider="telegram",
                            peer_type=("private" if getattr(event, "is_private", False)
                                       else "group" if getattr(event, "is_group", False)
                                       else "channel" if getattr(event, "is_channel", False)
                                       else "chat"),
                            peer_id=int(sender_id or 0),
                            chat_id=int(chat_id),
                            external_chat_id=str(chat_id),
                            external_msg_id=str(msg_id),
                            msg_id=int(msg_id),
                            text_value=text,
                            # model/key берём из meta_json ресурса (в dialog_service)
                            model_text=None,
                            temperature=None,
                        )
                        if not res:
                            # дубль (или пустое) -> не отвечаем
                            return

                        answer = (res.get("text") or "").strip()
                        if not answer:
                            return

                        sent = await event.reply(answer)

                        # проставим ids исходящего сообщения в БД
                        try:
                            await attach_outgoing_ids(
                                message_id=res.get("out_message_id"),
                                msg_id=getattr(sent, "id", None),
                                external_msg_id=str(getattr(sent, "id", "")) or None,
                            )
                        except Exception as e:
                            self._log(f"attach_outgoing_ids failed: {e!r}")

                    except Exception as e:
                        await self._set_state(
                            phase="error",
                            code="dialog_service_error",
                            message=str(e),
                        )
                        self._log(f"dialog_service_error: {e!r}")

                await self.client.run_until_disconnected()

            except asyncio.CancelledError:
                return
            except Exception as e:
                self._running = False
                await self._set_state(
                    phase="error",
                    code="telegram_runtime_error",
                    message=str(e),
                )
                self._log(f"telegram_runtime_error: {e!r}")
                await asyncio.sleep(2)
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
        # running = реально активная сессия, а не просто объект
        return {rid: "telegram" for rid, w in self._workers.items() if w.is_running}


session_registry = SessionRegistry()
