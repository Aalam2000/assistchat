"""
src/app/core/message_bus.py
────────────────────────────────────────────────────────────
Шина сообщений (in-memory async pub/sub).

Источники (Telegram-сессия, Telegram-бот, Facebook и др.) публикуют
сюда события через publish(). PROMPT-воркеры подписываются через
subscribe() на нужные им resource_id источников.

Интерфейс намеренно минимален — при необходимости заменяется
на Redis/NATS без изменений остального кода.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine


@dataclass
class MessageEvent:
    """Нормализованное входящее сообщение из любого источника."""

    # Откуда пришло
    source_type: str          # "telegram_session" | "telegram_bot" | "facebook" | ...
    source_rid: str           # resource_id источника (UUID строкой)

    # Отправитель
    peer_id: int              # числовой ID отправителя
    peer_type: str            # "private" | "group" | "channel" | "chat"
    chat_id: int | None       # ID чата (None для private = peer_id)
    sender_username: str | None

    # Сообщение
    msg_id: int | None
    external_chat_id: str     # строковый ID чата для дедупа
    external_msg_id: str      # строковый ID сообщения для дедупа
    text: str                 # текст (может быть пустым для медиа)
    msg_type: str = "text"    # "text" | "voice" | "file" | "image"

    # Человекочитаемые названия (для форматирования уведомлений)
    source_label: str | None = None   # название ресурса-источника (как в интерфейсе)
    chat_name: str | None = None      # название группы/канала (None для личок)
    chat_username: str | None = None  # @username группы/канала (None для лички)

    # Сырые данные (для будущих расширений)
    raw: dict[str, Any] = field(default_factory=dict)


# Тип колбэка: async-функция принимающая MessageEvent
EventCallback = Callable[[MessageEvent], Coroutine[Any, Any, None]]


class MessageBus:
    """
    Простой async pub/sub брокер сообщений.

    Подписка: subscribe(source_rid, callback)
    Публикация: await publish(source_rid, event)
    Все подписчики вызываются конкурентно (gather).
    Ошибка в одном подписчике не роняет остальных.
    """

    def __init__(self) -> None:
        # source_rid → list of callbacks
        self._subscribers: dict[str, list[EventCallback]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, source_rid: str, callback: EventCallback) -> None:
        async with self._lock:
            self._subscribers.setdefault(source_rid, [])
            if callback not in self._subscribers[source_rid]:
                self._subscribers[source_rid].append(callback)

    async def unsubscribe(self, source_rid: str, callback: EventCallback) -> None:
        async with self._lock:
            subs = self._subscribers.get(source_rid, [])
            if callback in subs:
                subs.remove(callback)

    async def publish(self, source_rid: str, event: MessageEvent) -> None:
        async with self._lock:
            callbacks = list(self._subscribers.get(source_rid, []))

        if not callbacks:
            return

        async def _safe_call(cb: EventCallback) -> None:
            try:
                await cb(event)
            except Exception as e:
                print(f"[BUS] callback error for source={source_rid}: {e!r}", flush=True)

        await asyncio.gather(*(_safe_call(cb) for cb in callbacks))

    def subscriber_count(self, source_rid: str) -> int:
        return len(self._subscribers.get(source_rid, []))


# Глобальный singleton — импортируется всеми воркерами
bus = MessageBus()
