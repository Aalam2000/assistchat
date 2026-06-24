# src/app/resources/chat_base/notifier.py
from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from src.app.core.db import SessionLocal
from src.app.resources.chat_base.meta import (
    accept_candidate,
    normalize_meta,
    reject_candidate,
    resolve_pending,
)
from src.models.resource import Resource


def _format_card(candidate: dict[str, Any]) -> str:
    title = candidate.get("title") or "—"
    link = candidate.get("link") or "—"
    members = candidate.get("members")
    desc = (candidate.get("description") or "")[:400]
    week = candidate.get("week_message_count")
    last = candidate.get("last_post_at") or "—"
    query = candidate.get("query") or "—"
    return (
        f"<b>{title}</b>\n"
        f"Ссылка: {link}\n"
        f"ID: {candidate.get('external_id')}\n"
        f"Участников: {members if members is not None else '—'}\n"
        f"Сообщений за неделю: {week if week is not None else '—'}\n"
        f"Последний пост: {last}\n"
        f"Запрос: {query}\n\n"
        f"{desc}"
    ).strip()


def _keyboard(pending_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Принять", callback_data=f"cb:a:{pending_id}"
                ),
                InlineKeyboardButton(
                    text="Пропустить", callback_data=f"cb:s:{pending_id}"
                ),
            ]
        ]
    )


class ChatBaseNotifier:
    """Собственный бот ресурса chat_base: карточки и callback accept/skip."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._bots: dict[str, Bot] = {}
        self._dispatchers: dict[str, Dispatcher] = {}

    async def send_candidate(
        self,
        *,
        resource_id: str,
        bot_token: str,
        owner_id: int,
        pending_id: str,
        candidate: dict[str, Any],
    ) -> None:
        await self.ensure_polling(resource_id, bot_token)
        bot = self._bots[resource_id]
        await bot.send_message(
            owner_id,
            _format_card(candidate),
            reply_markup=_keyboard(pending_id),
            parse_mode=ParseMode.HTML,
        )

    async def ensure_polling(self, resource_id: str, bot_token: str) -> None:
        rid = str(resource_id)
        if rid in self._tasks and not self._tasks[rid].done():
            return

        bot = Bot(
            token=bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        dp = Dispatcher()
        self._bots[rid] = bot
        self._dispatchers[rid] = dp

        @dp.callback_query(F.data.startswith("cb:"))
        async def on_callback(cq: CallbackQuery) -> None:
            await _handle_callback(cq, rid)

        async def _poll() -> None:
            try:
                await dp.start_polling(bot, handle_signals=False)
            except asyncio.CancelledError:
                pass
            finally:
                try:
                    await bot.session.close()
                except Exception:
                    pass

        self._tasks[rid] = asyncio.create_task(_poll())

    async def stop(self, resource_id: str) -> None:
        rid = str(resource_id)
        task = self._tasks.pop(rid, None)
        dp = self._dispatchers.pop(rid, None)
        bot = self._bots.pop(rid, None)
        if dp:
            try:
                await dp.stop_polling()
            except Exception:
                pass
        if task:
            task.cancel()
            try:
                await task
            except Exception:
                pass
        if bot:
            try:
                await bot.session.close()
            except Exception:
                pass


async def _handle_callback(cq: CallbackQuery, bound_rid: str) -> None:
    data = cq.data or ""
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "cb":
        await cq.answer("Неверные данные")
        return
    action, pending_id = parts[1], parts[2]
    if action not in ("a", "s"):
        await cq.answer("Неизвестное действие")
        return

    msg = "Готово"
    db = SessionLocal()
    try:
        row = db.get(Resource, UUID(bound_rid))
        if not row or row.provider != "chat_base":
            await cq.answer("Ресурс не найден")
            return
        meta = normalize_meta(row.meta_json)
        candidate = resolve_pending(meta, pending_id)
        if not candidate:
            await cq.answer("Кандидат уже обработан")
            return
        platform = str(
            candidate.get("platform") or meta.get("platform") or "telegram"
        )
        if action == "a":
            ok = accept_candidate(meta, candidate, platform)
            msg = "Принято" if ok else "Лимит 200 или дубликат"
        else:
            reject_candidate(meta, candidate)
            msg = "Пропущено"
        row.meta_json = meta
        db.add(row)
        db.commit()
    finally:
        db.close()

    try:
        if cq.message:
            suffix = "✅ принято" if action == "a" else "❌ пропущено"
            await cq.message.edit_text(f"{cq.message.text}\n\n— {suffix}")
    except Exception:
        pass
    await cq.answer(msg)


notifier = ChatBaseNotifier()
