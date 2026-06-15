# src/app/resources/prompt/prompt_worker.py
"""
PROMPT-воркер.

Жизненный цикл:
  1. Читает настройки из DB (sources, filters, ai, prompt.steps)
  2. Подписывается на MessageBus для выбранных источников
  3. Для каждого входящего сообщения:
       a. Применяет фильтры (тип чата, whitelist/blacklist)
       b. Последовательно выполняет шаги трёх типов:
          - condition : правила без AI (ключевые слова / отправитель)
          - ai        : AI анализ, действие: continue / stop / notify_owner
          - notify    : уведомить хозяина (прямо или через AI форматирование)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from src.app.core.db import SessionLocal
from src.app.core.message_bus import MessageEvent, bus
from src.models.resource import Resource
from src.models.user import User

UPLOADS_BASE = Path("/app/uploads")

# Оптимальная модель по умолчанию для каждого провайдера
DEFAULT_MODELS: dict[str, str] = {
    "creds.openai_api_key":    "gpt-4o-mini",
    "creds.openai_admin_key":  "gpt-4o-mini",
    "creds.gemini_api_key":    "gemini-2.0-flash",
    "creds.anthropic_api_key": "claude-3-5-haiku-latest",
    "creds.groq_api_key":      "llama-3.1-8b-instant",
    "creds.deepseek_api_key":  "deepseek-chat",
    "creds.mistral_api_key":   "mistral-small-latest",
    "creds.xai_api_key":       "grok-2-1212",
}


def _utcnow():
    return datetime.now(timezone.utc)


def _log(label: str, rid: str, msg: str) -> None:
    print(f"[PROMPT] {label}({rid}) {msg}", flush=True)


def _read_context_file(rel_path: str | None) -> str:
    if not rel_path:
        return ""
    try:
        p = UPLOADS_BASE / rel_path
        if not p.exists():
            return ""
        text = p.read_text(encoding="utf-8", errors="replace")
        return text[:8000]  # не перегружаем контекст
    except Exception:
        return ""


def _passes_filters(event: MessageEvent, filters: dict, label: str = "") -> bool:
    if event.peer_type == "private" and not filters.get("reply_private", True):
        print(f"[FILTER] {label} skip: peer_type=private disabled", flush=True)
        return False
    if event.peer_type == "group" and not filters.get("reply_groups", False):
        print(f"[FILTER] {label} skip: peer_type=group disabled", flush=True)
        return False
    if event.peer_type == "channel" and not filters.get("reply_channels", False):
        print(f"[FILTER] {label} skip: peer_type=channel disabled", flush=True)
        return False

    def _norm(s: str) -> str:
        """Нормализуем запись: t.me/user → user, @user → user, https://t.me/user → user"""
        s = s.strip().lower()
        for prefix in ("https://t.me/", "http://t.me/", "t.me/", "@"):
            if s.startswith(prefix):
                s = s[len(prefix):]
                break
        return s

    whitelist = [str(x) for x in (filters.get("whitelist") or []) if x]
    blacklist = [str(x) for x in (filters.get("blacklist") or []) if x]

    peer = str(event.peer_id)
    chat = str(event.chat_id or "")
    uname = _norm(event.sender_username or "")

    wl_clean = [_norm(w) for w in whitelist]
    bl_clean = [_norm(b) for b in blacklist]

    print(f"[FILTER] {label} peer={peer} chat={chat} uname={uname!r} wl={wl_clean} bl={bl_clean}", flush=True)

    if wl_clean:
        in_white = peer in wl_clean or chat in wl_clean or uname in wl_clean
        if not in_white:
            print(f"[FILTER] {label} skip: not in whitelist", flush=True)
            return False

    if bl_clean:
        in_black = peer in bl_clean or chat in bl_clean or uname in bl_clean
        if in_black:
            print(f"[FILTER] {label} skip: blacklist hit uname={uname!r} chat={chat}", flush=True)
            return False

    return True


async def _get_api_key_value(api_keys_resource_id: str, api_key_field: str, user_id) -> str | None:
    db = SessionLocal()
    try:
        r = db.query(Resource).filter(
            Resource.id == api_keys_resource_id,
            Resource.user_id == user_id,
            Resource.provider == "api_keys",
        ).first()
        if not r:
            return None
        meta = r.meta_json or {}
        creds = meta.get("creds") or {}
        short = api_key_field.split(".", 1)[1] if "." in api_key_field else api_key_field
        return (creds.get(short) or "").strip() or None
    finally:
        db.close()


async def _call_ai(
    api_key: str,
    api_key_field: str,
    model: str,
    system: str,
    messages: list[dict],
) -> str | None:
    """Вызов AI через ai_transport."""
    try:
        from src.app.core.ai_transport import AIChatConfig, chat, provider_from_key_field
        provider = provider_from_key_field(api_key_field)
        cfg = AIChatConfig(
            provider=provider,
            api_key=api_key,
            model=model,
            temperature=0.3,
        )
        full_messages: list[dict] = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)
        result = await chat(cfg=cfg, messages=full_messages)
        if not result.ok:
            print(f"[PROMPT] _call_ai provider error: {result.error}", flush=True)
            return None
        return result.text or None
    except Exception as e:
        print(f"[PROMPT] _call_ai error: {e!r}", flush=True)
        return None


async def _notify_owner(
    bot_rid: str | None,
    owner_tg_id: int | None,
    text: str,
) -> None:
    """Отправить текстовое уведомление хозяину через Telegram Bot."""
    if not bot_rid or not owner_tg_id:
        print(f"[PROMPT] notify_owner: no bot_rid or owner_tg_id", flush=True)
        return
    try:
        from src.app.resources.telegram_bot.bot import bot_registry
        worker = bot_registry.get(bot_rid)
        if not worker:
            print(f"[PROMPT] notify_owner: bot rid={bot_rid} not running", flush=True)
            return
        await worker.send_message(owner_tg_id, text)
    except Exception as e:
        print(f"[PROMPT] notify_owner error: {e!r}", flush=True)


async def _forward_to_owner(
    session_rid: str,
    owner_tg_id: int,
    from_chat_id: int,
    msg_id: int,
    header: str,
    bot_rid: str | None,
) -> None:
    """Переслать оригинальное сообщение через Telethon + отправить заголовок через бот."""
    try:
        from src.app.resources.telegram.telegram import session_registry
        worker = session_registry.get(session_rid)
        if worker:
            # Сначала шлём заголовок через бота
            if bot_rid:
                from src.app.resources.telegram_bot.bot import bot_registry
                bot = bot_registry.get(bot_rid)
                if bot:
                    await bot.send_message(owner_tg_id, header)
            # Затем форвардим оригинал через Telethon
            await worker.forward_message(
                to_peer=owner_tg_id,
                from_chat_id=from_chat_id,
                msg_id=msg_id,
            )
        else:
            # Telethon недоступен — fallback на текст через бота
            await _notify_owner(bot_rid, owner_tg_id, header)
    except Exception as e:
        print(f"[PROMPT] _forward_to_owner error: {e!r}", flush=True)


class PromptWorker:
    """
    Воркер одного PROMPT-ресурса.
    Подписывается на шину, фильтрует, запускает шаги, уведомляет.
    """

    def __init__(self, resource: Resource):
        self.resource = resource
        self._subscribed_rids: list[str] = []
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._running = False
        self._semaphore = asyncio.Semaphore(3)  # не более 3 параллельных обработок

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def update_resource(self, resource: Resource) -> None:
        self.resource = resource

    def launch(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        self._running = False
        await self._unsubscribe_all()

    def _rid(self) -> str:
        return str(self.resource.id)

    def _label(self) -> str:
        return self.resource.label or self._rid()

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

    async def _unsubscribe_all(self) -> None:
        for src_rid in self._subscribed_rids:
            try:
                await bus.unsubscribe(src_rid, self._on_message)
            except Exception:
                pass
        self._subscribed_rids.clear()

    async def _on_message(self, event: MessageEvent) -> None:
        if self._stop.is_set():
            return
        async with self._semaphore:
            await self._process(event)

    async def _process(self, event: MessageEvent) -> None:  # noqa: C901
        rid = self._rid()
        label = self._label()

        # Перечитываем актуальные настройки
        db = SessionLocal()
        try:
            r = db.get(Resource, self.resource.id)
            if not r or r.status != "active":
                return
            u = db.get(User, r.user_id) if r.user_id else None
            if not u or not getattr(u, "bot_enabled", False):
                return
            meta = r.meta_json or {}
            user_id = r.user_id
        finally:
            db.close()

        filters = meta.get("filters") or {}
        ai_cfg = meta.get("ai") or {}
        prompt_cfg = meta.get("prompt") or {}
        sources = meta.get("sources") or {}
        owner_cfg = meta.get("owner") or {}

        # Фильтрация (только для сессий, не для ботов)
        if event.source_type == "telegram_session":
            if not _passes_filters(event, filters, label=label):
                return

        steps: list[dict] = prompt_cfg.get("steps") or []
        if not steps:
            _log(label, rid, "skip: no steps configured")
            return

        # Проверяем — нужен ли AI вообще
        needs_ai = any(
            s.get("type") in ("ai", "notify") and
            (s.get("type") == "ai" or s.get("notify_mode") == "ai_formatted")
            for s in steps
        )

        api_key: str | None = None
        api_key_field: str | None = None
        model: str | None = None

        if needs_ai:
            api_keys_rid = ai_cfg.get("api_keys_resource_id")
            api_key_field = ai_cfg.get("api_key_field")
            model = ai_cfg.get("model")
            if not api_keys_rid or not api_key_field or not model:
                _log(label, rid, "skip: AI steps present but AI not configured")
                return
            api_key = await _get_api_key_value(api_keys_rid, api_key_field, user_id)
            if not api_key:
                _log(label, rid, "skip: API key not found")
                return

        # Контекст
        system_text = (prompt_cfg.get("system") or "").strip()
        context_text = (prompt_cfg.get("context") or "").strip()
        context_file = _read_context_file(prompt_cfg.get("context_file"))

        full_system = system_text
        if context_text:
            full_system += f"\n\n--- КОНТЕКСТ ---\n{context_text}"
        if context_file:
            full_system += f"\n\n--- ФАЙЛ КОНТЕКСТА ---\n{context_file}"

        # Входящее сообщение
        incoming_text = event.text or f"[{event.msg_type}]"

        # Формируем читаемую строку источника: "Сессия, Группа, @user"
        source_parts: list[str] = []
        if event.source_label:
            source_parts.append(event.source_label)
        if event.chat_name:
            source_parts.append(event.chat_name)
        if event.sender_username:
            source_parts.append(f"@{event.sender_username}")
        elif event.peer_id:
            source_parts.append(f"id{event.peer_id}")
        source_info = ", ".join(source_parts) if source_parts else event.source_type

        # Накопленный диалог (используется в AI-шагах)
        accumulated: list[dict] = [
            {"role": "user", "content": f"{source_info}\n\nСообщение:\n{incoming_text}"}
        ]

        bot_rid = sources.get("telegram_bot_rid")
        owner_tg_id = owner_cfg.get("telegram_user_id")

        _log(label, rid, f"processing {len(steps)} steps | msg={incoming_text[:80]!r}")

        for i, step in enumerate(steps):
            step_name = step.get("name") or f"Шаг {i + 1}"
            step_type = (step.get("type") or "condition").lower()

            # ── ТИП 1: УСЛОВИЕ (без AI) ──────────────────────────────────────
            if step_type == "condition":
                mode     = (step.get("condition_mode") or "keywords").lower()
                on_match = (step.get("on_match")    or "continue").lower()
                on_no_match = (step.get("on_no_match") or "stop").lower()
                matched = False

                if mode == "keywords":
                    keywords = [k.strip().lower() for k in (step.get("keywords") or []) if k.strip()]
                    if keywords:
                        text_lower = incoming_text.lower()
                        matched = any(kw in text_lower for kw in keywords)
                    else:
                        matched = True  # пустой список → всегда совпадает

                elif mode == "sender":
                    senders = [s.strip().lower().lstrip("@") for s in (step.get("senders") or []) if s.strip()]
                    if senders:
                        uname = (event.sender_username or "").lstrip("@").lower()
                        peer_str = str(event.peer_id)
                        matched = uname in senders or peer_str in senders
                    else:
                        matched = True

                decision = on_match if matched else on_no_match
                _log(label, rid, f"step[{i}] {step_name} condition={mode} matched={matched} → {decision}")
                if decision == "stop":
                    return  # игнорируем это сообщение

            # ── ТИП 2: AI АНАЛИЗ ────────────────────────────────────────────
            elif step_type == "ai":
                instruction = (step.get("ai_instruction") or "").strip()
                action = (step.get("ai_action") or "continue").lower()

                if not instruction:
                    _log(label, rid, f"step[{i}] {step_name} ai: empty instruction, skip")
                    continue

                step_system = full_system
                if instruction:
                    step_system += f"\n\n--- ЗАДАЧА: {step_name} ---\n{instruction}"

                response = await _call_ai(
                    api_key=api_key,  # type: ignore[arg-type]
                    api_key_field=api_key_field,  # type: ignore[arg-type]
                    model=model,  # type: ignore[arg-type]
                    system=step_system,
                    messages=accumulated,
                )

                if not response:
                    _log(label, rid, f"step[{i}] {step_name} ai: empty response → abort")
                    return

                accumulated.append({"role": "assistant", "content": response})
                _log(label, rid, f"step[{i}] {step_name} ai [{action}]: {response[:120]!r}")

                if action == "stop":
                    return

                if action == "notify_owner":
                    notification = (
                        f"📌 *{label}*\n"
                        f"{source_info}\n"
                        f"Сообщение: {incoming_text}\n\n"
                        f"💡 {response}"
                    )
                    await _notify_owner(bot_rid, owner_tg_id, notification)
                    _log(label, rid, f"notified owner tg_id={owner_tg_id}")
                # action == "continue" → следующий шаг

            # ── ТИП 3: УВЕДОМИТЬ ХОЗЯИНА ────────────────────────────────────
            elif step_type == "notify":
                notify_mode = (step.get("notify_mode") or "direct").lower()

                if notify_mode == "direct":
                    _media_labels = {
                        "album": "📷 Альбом",
                        "photo": "🖼 Фото",
                        "voice": "🎤 Голосовое",
                        "file": "📎 Файл",
                    }
                    if incoming_text:
                        if event.msg_type in _media_labels:
                            body = f"{_media_labels[event.msg_type]}: {incoming_text}"
                        else:
                            body = incoming_text
                    else:
                        body = _media_labels.get(event.msg_type, f"[{event.msg_type}]")

                    header = f"📌 *{label}*\n{source_info}"

                    # Для альбомов и фото — скачиваем через Telethon и шлём как медиагруппу
                    sent_as_media = False
                    if (
                        event.msg_type in ("album", "photo")
                        and event.source_type == "telegram_session"
                        and event.chat_id and event.msg_id
                        and bot_rid and owner_tg_id
                    ):
                        try:
                            from src.app.resources.telegram.telegram import session_registry
                            from src.app.resources.telegram_bot.bot import bot_registry as _bot_reg

                            tg_worker = session_registry.get(event.source_rid)
                            bot_worker = _bot_reg.get(bot_rid)
                            if tg_worker and bot_worker:
                                grouped_id = (event.raw or {}).get("grouped_id")
                                photos, album_caption = await tg_worker.download_album(
                                    from_chat_id=event.chat_id,
                                    msg_id=event.msg_id,
                                    grouped_id=grouped_id,
                                )
                                if photos:
                                    # Используем текст из download_album (там подпись точно есть)
                                    final_text = album_caption or incoming_text
                                    caption = f"{header}\n\n{final_text}" if final_text else header
                                    sent_as_media = await bot_worker.send_media_group(
                                        owner_tg_id, photos, caption
                                    )
                                    _log(label, rid, f"step[{i}] {step_name} notify album → {len(photos)} photos → owner={owner_tg_id}")
                        except Exception as _e:
                            _log(label, rid, f"step[{i}] album download error: {_e!r}")

                    if not sent_as_media:
                        notification = f"{header}\n\n{body}"
                        await _notify_owner(bot_rid, owner_tg_id, notification)
                    _log(label, rid, f"step[{i}] {step_name} notify direct → owner={owner_tg_id}")

                elif notify_mode == "ai_formatted":
                    instruction = (step.get("notify_instruction") or "Сформируй краткое уведомление хозяину").strip()
                    step_system = full_system + f"\n\n--- ЗАДАЧА: {step_name} ---\n{instruction}"
                    response = await _call_ai(
                        api_key=api_key,  # type: ignore[arg-type]
                        api_key_field=api_key_field,  # type: ignore[arg-type]
                        model=model,  # type: ignore[arg-type]
                        system=step_system,
                        messages=accumulated,
                    )
                    if response:
                        await _notify_owner(bot_rid, owner_tg_id, response)
                        _log(label, rid, f"step[{i}] {step_name} notify ai_formatted → owner={owner_tg_id}")
                    else:
                        _log(label, rid, f"step[{i}] {step_name} notify ai_formatted: empty response")

            else:
                _log(label, rid, f"step[{i}] {step_name}: unknown type={step_type!r}, skip")

    async def _run(self) -> None:
        rid = self._rid()
        label = self._label()
        _log(label, rid, "start()")

        while not self._stop.is_set():
            await self._unsubscribe_all()

            db = SessionLocal()
            try:
                r = db.get(Resource, self.resource.id)
                if not r:
                    _log(label, rid, "resource not found → stop")
                    return
                u = db.get(User, r.user_id) if r.user_id else None

                if not u or not getattr(u, "bot_enabled", False):
                    await self._set_state(phase="paused")
                    _log(label, rid, "paused: user.bot_enabled=false")
                    return

                if r.status != "active":
                    await self._set_state(phase="paused")
                    _log(label, rid, f"paused: status={r.status}")
                    return

                meta = r.meta_json or {}
                sources = meta.get("sources") or {}
                session_rid = sources.get("telegram_session_rid")
                bot_rid = sources.get("telegram_bot_rid")
            finally:
                db.close()

            if not session_rid and not bot_rid:
                await self._set_state(
                    phase="error",
                    code="prompt_no_sources",
                    message="Не выбран ни один источник",
                )
                _log(label, rid, "error: no sources")
                await asyncio.sleep(10)
                continue

            # Подписываемся на источники
            for src_rid in filter(None, [session_rid, bot_rid]):
                await bus.subscribe(src_rid, self._on_message)
                self._subscribed_rids.append(src_rid)

            self._running = True
            await self._set_state(phase="running", code=None, message=None)
            _log(label, rid, f"running: subscribed to {self._subscribed_rids}")

            # Ждём пока не остановят или не изменится конфиг
            while not self._stop.is_set():
                await asyncio.sleep(5)
                # Проверяем не изменился ли статус в DB
                db = SessionLocal()
                try:
                    r = db.get(Resource, self.resource.id)
                    if not r or r.status != "active":
                        break
                finally:
                    db.close()

            self._running = False
            await self._unsubscribe_all()

            if self._stop.is_set():
                return

        self._running = False


class PromptRegistry:
    def __init__(self):
        self._workers: dict[str, PromptWorker] = {}
        self._lock = asyncio.Lock()

    async def ensure_started(self, resource: Resource) -> PromptWorker:
        async with self._lock:
            rid = str(resource.id)
            w = self._workers.get(rid)
            if not w:
                w = PromptWorker(resource)
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
        return {rid: "prompt" for rid, w in self._workers.items() if w.is_running}


prompt_registry = PromptRegistry()
