# src/app/resources/chat_base/notifier.py
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from aiogram import Bot
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

from src.app.resources.chat_base.callback_data import (
    build_callback_data,
    parse_callback_data,
    parse_callback_data_legacy,
)

logger = logging.getLogger(__name__)


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


def _keyboard(chat_base_rid: str, pending_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Принять",
                    callback_data=build_callback_data(
                        "a", chat_base_rid, pending_id
                    ),
                ),
                InlineKeyboardButton(
                    text="Пропустить",
                    callback_data=build_callback_data(
                        "s", chat_base_rid, pending_id
                    ),
                ),
            ]
        ]
    )


def _find_resource_by_pending(
    db, pending_id: str
) -> tuple[Resource | None, dict[str, Any] | None]:
    rows = (
        db.query(Resource)
        .filter(Resource.provider == "chat_base")
        .all()
    )
    for row in rows:
        meta = normalize_meta(row.meta_json)
        if pending_id in (meta.get("pending") or {}):
            return row, meta
    return None, None


class ChatBaseNotifier:
    """Отправка карточек через Bot API; callback — в telegram_bot botworker."""

    async def send_candidate(
        self,
        *,
        resource_id: str,
        bot_token: str,
        owner_id: int,
        pending_id: str,
        candidate: dict[str, Any],
    ) -> None:
        bot = Bot(
            token=bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        try:
            await bot.send_message(
                owner_id,
                _format_card(candidate),
                reply_markup=_keyboard(str(resource_id), pending_id),
                parse_mode=ParseMode.HTML,
            )
            logger.info(
                "chat_base card sent rid=%s pending=%s owner=%s eid=%s",
                resource_id,
                pending_id,
                owner_id,
                candidate.get("external_id"),
            )
        finally:
            await bot.session.close()


async def route_callback_query(cq: CallbackQuery) -> None:
    data = cq.data or ""
    parsed = parse_callback_data(data)
    if parsed:
        action, cb_rid, pending_id = parsed
        await _handle_callback(cq, cb_rid, action, pending_id)
        return

    legacy = parse_callback_data_legacy(data)
    if legacy:
        action, pending_id = legacy
        db = SessionLocal()
        try:
            row, meta = _find_resource_by_pending(db, pending_id)
            if not row or meta is None:
                logger.warning(
                    "chat_base callback legacy pending not found pending=%s",
                    pending_id,
                )
                await cq.answer("Кандидат уже обработан")
                return
            await _handle_callback(
                cq, str(row.id), action, pending_id, meta_prefetched=meta
            )
        finally:
            db.close()
        return

    logger.warning("chat_base callback bad data=%r", data)
    await cq.answer("Неверные данные")


async def _handle_callback(
    cq: CallbackQuery,
    chat_base_rid: str,
    action: str,
    pending_id: str,
    *,
    meta_prefetched: dict[str, Any] | None = None,
) -> None:
    msg = "Готово"
    db = SessionLocal()
    try:
        row = db.get(Resource, UUID(chat_base_rid))
        if not row or row.provider != "chat_base":
            logger.warning(
                "chat_base callback resource missing rid=%s pending=%s",
                chat_base_rid,
                pending_id,
            )
            await cq.answer("Ресурс не найден")
            return
        meta = meta_prefetched or normalize_meta(row.meta_json)
        candidate = resolve_pending(meta, pending_id)
        if not candidate:
            logger.info(
                "chat_base callback pending gone rid=%s pending=%s",
                chat_base_rid,
                pending_id,
            )
            await cq.answer("Кандидат уже обработан")
            return
        platform = str(
            candidate.get("platform") or meta.get("platform") or "telegram"
        )
        if action == "a":
            ok = accept_candidate(meta, candidate, platform)
            msg = "Принято" if ok else "Лимит 200 или дубликат"
            logger.info(
                "chat_base accept rid=%s pending=%s eid=%s ok=%s accepted=%s",
                chat_base_rid,
                pending_id,
                candidate.get("external_id"),
                ok,
                len((meta.get("accepted") or {}).get(platform) or []),
            )
        else:
            reject_candidate(meta, candidate)
            msg = "Пропущено"
            logger.info(
                "chat_base skip rid=%s pending=%s eid=%s",
                chat_base_rid,
                pending_id,
                candidate.get("external_id"),
            )
        row.meta_json = meta
        db.add(row)
        db.commit()
    except Exception:
        logger.exception(
            "chat_base callback failed rid=%s pending=%s action=%s",
            chat_base_rid,
            pending_id,
            action,
        )
        await cq.answer("Ошибка сохранения")
        return
    finally:
        db.close()

    try:
        if cq.message:
            suffix = "✅ принято" if action == "a" else "❌ пропущено"
            base = cq.message.text or cq.message.caption or ""
            await cq.message.edit_text(f"{base}\n\n— {suffix}")
    except Exception as e:
        logger.warning("chat_base callback edit_text failed: %r", e)
    await cq.answer(msg)


notifier = ChatBaseNotifier()
