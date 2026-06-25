# src/app/resources/chat_base/assist.py
from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session as SASession

ASSIST_SYSTEM = """\
Ты помогаешь собирать поисковые запросы для Telegram.
Ищем публичные группы и каналы по НАЗВАНИЮ (Search по title).

На выход: только список коротких поисковых фраз — как реально называют чаты.

Правила:
- 15–25 фраз, по одной на строку, без нумерации и пояснений
- Коротко: 1-2 слова, не предложения
- Языки берешь из темы. Если нет - EN.
- Используешь Синонимы
- Без дубликатов и без мусора вроде «заказы Заказы программисту»
- Только фразы для поиска названий групп, не хештеги и не @username\
"""


def build_assist_user_message(label: str, topic: str) -> str:
    name = (label or "").strip() or "—"
    desc = (topic or "").strip() or "—"
    return (
        f"Вот тебе:\n"
        f"Название базы: {name}\n"
        f"Описание темы: {desc}"
    )


def parse_queries_from_ai(text: str) -> list[str]:
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"^[\-*•\d.)]+\s*", "", line).strip()
        line = line.strip('"\'`')
        if not line or line.startswith("#") or line.startswith("@"):
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
    return out


def get_api_key_value(
    db: SASession,
    api_keys_resource_id: str,
    api_key_field: str,
    user_id: int,
) -> str | None:
    from uuid import UUID

    from src.models.resource import Resource

    try:
        rid = UUID(str(api_keys_resource_id))
    except Exception:
        return None
    r = db.query(Resource).filter(
        Resource.id == rid,
        Resource.user_id == user_id,
        Resource.provider == "api_keys",
    ).first()
    if not r:
        return None
    creds = (r.meta_json or {}).get("creds") or {}
    field = api_key_field
    short = field.split(".", 1)[1] if "." in field else field
    return (creds.get(short) or "").strip() or None


async def generate_queries_ai(
    db: SASession,
    *,
    user_id: int,
    label: str,
    topic: str,
    ai_cfg: dict[str, Any],
) -> tuple[list[str], str | None]:
    api_keys_rid = ai_cfg.get("api_keys_resource_id")
    api_key_field = ai_cfg.get("api_key_field")
    model = ai_cfg.get("model")
    if not api_keys_rid or not api_key_field or not model:
        return [], "Настройте AI: ресурс API Keys, ключ и модель"

    api_key = get_api_key_value(
        db, str(api_keys_rid), str(api_key_field), user_id
    )
    if not api_key:
        return [], "API ключ не найден"

    user_msg = build_assist_user_message(label, topic)
    if (topic or "").strip() == "" and (label or "").strip() == "":
        return [], "Укажите название базы или описание темы"

    try:
        from src.app.core.ai_transport import (
            AIChatConfig,
            chat,
            provider_from_key_field,
        )

        provider = provider_from_key_field(str(api_key_field))
        cfg = AIChatConfig(
            provider=provider,
            api_key=api_key,
            model=str(model),
            temperature=0.4,
        )
        result = await chat(
            cfg=cfg,
            messages=[
                {"role": "system", "content": ASSIST_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
        )
        if not result.ok or not result.text:
            err = result.error or "AI не вернул ответ"
            return [], str(err)
        queries = parse_queries_from_ai(result.text)
        if not queries:
            return [], "AI вернул пустой список"
        return queries, None
    except Exception as e:
        return [], f"Ошибка AI: {e!r}"
