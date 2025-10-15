"""
src/app/resources/telegram/telegram.py
──────────────────────────────────────
Фоновый воркер Telegram-ресурса AssistChat.

Назначение:
    • Поддерживает активное соединение с Telegram через Telethon;
    • Обрабатывает входящие сообщения, применяет фильтры и промпты;
    • Формирует ответы через TelegramDialogEngine (в т.ч. OpenAI);
    • Ведёт журнал сообщений, расход токенов и ошибки.
"""
import asyncio
from datetime import datetime, timezone

from telethon import TelegramClient, events
from telethon.sessions import StringSession

from src.app.core.db import SessionLocal
from src.models.message import Message
from src.models.resource import Resource
from src.models.user import User
from src.app.resources.telegram.openai_client import OpenAIClient


class TelegramWorker:
    """Фоновый обработчик Telegram-ресурса."""

    def __init__(self, resource: Resource):
        self.resource = resource
        self.client: TelegramClient | None = None
        self.dialog_engine = None
        self._running = False

    async def start(self):
        """Запуск воркера Telegram (устойчивый, с автопереподключением, транскрипцией и режимом ответов)."""
        print(f"[DEBUG][TG][{self.resource.id}] start() CALLED")

        while True:
            db = SessionLocal()
            try:
                user = db.get(User, self.resource.user_id)
                print(f"[DEBUG][TG][{self.resource.id}] user={user}, bot_enabled={getattr(user, 'bot_enabled', None)}")
                if not user or not getattr(user, "bot_enabled", False):
                    print(f"[TG][{self.resource.id}] user.bot_enabled=False → stop worker loop")
                    db.close()
                    break

                creds = (self.resource.meta_json or {}).get("creds", {})
                app_id = creds.get("app_id")
                app_hash = creds.get("app_hash")
                string_session = creds.get("string_session")
                print(
                    f"[DEBUG][TG][{self.resource.id}] creds: app_id={app_id}, app_hash={app_hash}, has_session={bool(string_session)}")

                if not app_id or not app_hash or not string_session:
                    raise ValueError(f"[TG][{self.resource.id}] missing credentials")

                # создаём Telethon-клиент и подключаемся
                self.client = TelegramClient(StringSession(string_session), app_id, app_hash)
                await self.client.connect()

                if await self.client.is_user_authorized():
                    print(f"[TG][{self.resource.id}] session authorized ✅")
                else:
                    print(f"[TG][{self.resource.id}] session NOT authorized ❌")
                    await asyncio.sleep(30)
                    continue

                print(f"[DEBUG][TG][{self.resource.id}] Telethon client connected = {self.client.is_connected()}")

                from src.app.resources.telegram.telegram_dialog import TelegramDialogEngine
                self.dialog_engine = TelegramDialogEngine(self.resource)
                print(f"[DEBUG][TG][{self.resource.id}] DialogEngine initialized")
                self._running = True

                @self.client.on(events.NewMessage)
                async def on_message(event):
                    print(f"[TG][{self.resource.id}] incoming msg from {event.sender_id}: {event.raw_text[:80]!r}")

                    db2 = SessionLocal()
                    r = db2.get(Resource, self.resource.id)
                    u = db2.get(User, self.resource.user_id)

                    # проверяем состояние ресурса
                    if not r or r.status != "active" or not getattr(u, "bot_enabled", False):
                        await self.stop()
                        db2.close()
                        return

                    if not self.apply_rules(event.message):
                        print(f"[TG][{self.resource.id}] blocked msg from {event.sender_id}")
                        db2.close()
                        return

                    # ---- определяем тип входящего сообщения ----
                    msg = event.message
                    mime = getattr(getattr(msg, "document", None), "mime_type", "") or ""
                    is_voice = bool(getattr(msg, "voice", None))
                    is_audio_doc = mime.startswith("audio/") or mime.endswith("/ogg") or mime.endswith("/opus")

                    text = (event.raw_text or "").strip()
                    audio_bytes = None

                    # ---- если голосовое — транскрибируем ----
                    if (is_voice or is_audio_doc) and not text:
                        try:
                            audio_bytes = await event.download_media(bytes=True)
                            oai = OpenAIClient(self.resource)
                            text = await oai.transcribe_audio(audio_bytes)
                            print(f"[TG][{self.resource.id}] voice → text: {text}")
                        except Exception as e:
                            print(f"[TG][{self.resource.id}] voice transcription error: {e}")
                            text = ""

                    if not text:
                        db2.close()
                        return

                    # ---- сохраняем входящее сообщение (текст или расшифровку аудио) ----
                    self._save_message(event, direction="in", text_override=text)

                    # ---- обращение к диалоговому движку ----
                    try:
                        prefer_voice_reply = is_voice or is_audio_doc
                        reply = await self.dialog_engine.handle_message(
                            event,
                            audio_bytes=audio_bytes if prefer_voice_reply else None,
                            prefer_voice_reply=prefer_voice_reply,
                        )
                    except Exception as e:
                        print(f"[TG][{self.resource.id}] dialog_engine error: {e}")
                        r.status = "error"
                        r.error_message = str(e)
                        db2.commit()
                        db2.close()
                        return

                    if not reply or not reply.get("text"):
                        db2.close()
                        return

                    # ---- ответ пользователю ----
                    try:
                        if reply.get("mode") == "voice" or prefer_voice_reply:
                            if reply.get("audio_bytes"):
                                await self.client.send_file(event.sender_id, reply["audio_bytes"], voice_note=True)
                            else:
                                # если OpenAI не вернул аудио — fallback на текст
                                await self.client.send_message(event.sender_id, reply["text"])
                        else:
                            await self.client.send_message(event.sender_id, reply["text"])
                    except Exception as e:
                        print(f"[TG][{self.resource.id}] send_message error: {e}")
                        self._mark_error(str(e))
                        db2.close()
                        return

                    # ---- сохраняем исходящее сообщение ----
                    self._save_message(event, direction="out")

                    # ---- учёт токенов и лимитов ----
                    used_tokens = int(reply.get("tokens") or 0)
                    r.usage_today = (r.usage_today or 0) + used_tokens
                    r.last_activity = datetime.now(timezone.utc)

                    limits = (r.meta_json or {}).get("limits", {})
                    token_limit = limits.get("tokens_limit")
                    if token_limit and used_tokens and r.usage_today >= token_limit:
                        if limits.get("autostop"):
                            print(f"[TG][{self.resource.id}] token limit reached → autostop")
                            r.status = "pause"
                            db2.commit()
                            await self.stop()
                            db2.close()
                            return

                    db2.commit()
                    db2.close()

                print(f"[TG][{self.resource.id}] Worker started successfully, waiting for messages...")
                await self.client.run_until_disconnected()

            except Exception as e:
                print(f"[TG][{self.resource.id}] start error:", e)
                self._mark_error(str(e))
                print(f"[TG][{self.resource.id}] retrying in 10s...")
                await asyncio.sleep(10)

            finally:
                db.close()

    async def stop(self):
        """Остановка воркера Telegram."""
        self._running = False
        if self.client:
            try:
                await self.client.disconnect()
            except Exception as e:
                print(f"[TG][{self.resource.id}] disconnect error:", e)
            self.client = None
        print(f"[TG][{self.resource.id}] Worker stopped")

    def _mark_error(self, message: str):
        """Фиксирует ошибку в БД."""
        db = SessionLocal()
        try:
            r = db.get(Resource, self.resource.id)
            if r:
                r.status = "error"
                r.error_message = message
                r.last_activity = datetime.now(timezone.utc)
                db.commit()
        finally:
            db.close()

    def apply_rules(self, message) -> bool:
        """Применяет фильтры whitelist/blacklist."""
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

    def _save_message(self, event, direction: str = "in", text_override: str | None = None,
                      msg_type: str | None = None):
        """Сохраняем сообщение в БД по схеме Message."""
        db = SessionLocal()
        try:
            # базовая мета из события
            peer_id = int(event.sender_id)
            chat_id = getattr(getattr(event, "chat", None), "id", None)
            peer_type = "private"
            if getattr(event, "is_group", False):
                peer_type = "group"
            elif getattr(event, "is_channel", False):
                peer_type = "channel"

            # входящий телеграм-id сообщения, если есть
            telegram_msg_id = getattr(getattr(event, "message", None), "id", None)

            # тип сообщения (text|voice|file)
            if not msg_type:
                m = getattr(event, "message", None)
                mime = getattr(getattr(m, "document", None), "mime_type", "") or ""
                is_voice = bool(getattr(m, "voice", None))
                is_audio_doc = mime.startswith("audio/") or mime.endswith("/ogg") or mime.endswith("/opus")
                if is_voice or is_audio_doc:
                    msg_type = "voice"
                elif getattr(m, "document", None):
                    msg_type = "file"
                else:
                    msg_type = "text"

            rec = Message(
                resource_id=self.resource.id,
                peer_id=peer_id,
                peer_type=peer_type,
                chat_id=chat_id,
                msg_id=telegram_msg_id,
                direction=direction,  # "in" | "out"
                msg_type=msg_type,  # "text" | "voice" | "file"
                text=(text_override or (event.raw_text or "").strip()) or None,
                tokens_in=None,
                tokens_out=None,
                latency_ms=None,
                service_id=str(self.resource.id),  # твой внутренний id сервиса
                provider="telegram",
                external_chat_id=str(chat_id) if chat_id is not None else None,
                external_msg_id=str(telegram_msg_id) if telegram_msg_id is not None else None,
            )
            db.add(rec)
            db.commit()
        except Exception as e:
            print(f"[TG][{self.resource.id}] save_message error: {e}")
            db.rollback()
        finally:
            db.close()

    async def send_message(self, peer_id: int, text: str):
        """Отправляет сообщение вручную (из интерфейса)."""
        if not self.client:
            raise RuntimeError("Telegram client not running")

        try:
            sent = await self.client.send_message(peer_id, text)
            self._save_message(sent, direction="out")

            # обновляем статистику
            db = SessionLocal()
            r = db.get(Resource, self.resource.id)
            if r:
                r.usage_today = (r.usage_today or 0)
                r.last_activity = datetime.now(timezone.utc)
                db.commit()
            db.close()
            return sent

        except Exception as e:
            print(f"[TG][{self.resource.id}] send_message error:", e)
            self._mark_error(str(e))
            raise
