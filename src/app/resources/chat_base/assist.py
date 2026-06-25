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
- Язык фраз:
  * по умолчанию — только EN (латиница, английские слова)
  * если в названии/описании явно указан один язык — все фразы на нём
  * если указано несколько языков (EN, RU, AZ …) — фразы на КАЖДОМ языке,
    примерно поровну; не своди всё к одному языку
  * явное указание: коды EN/RU/AZ, слова «на русском», «English», «Azərbaycan»…
  * кириллица в названии/описании сама по себе — НЕ указание языка
  * если язык не указан явно — все фразы на EN
- Используешь синонимы и термины ниши (freelance, developer, python…)
- Без дубликатов и без склеивания всего описания с jobs/freelance
- Только фразы для поиска названий групп, не хештеги и не @username\
"""

_LANG_CODES = re.compile(
    r"(?i)\b(en|ru|az|de|fr|tr|es|ua|uk)\b"
)

_LANG_NAME_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\b(english|anglais)\b"), "EN"),
    (re.compile(r"(?i)\b(russian|русск\w*|по-русски)\b"), "RU"),
    (re.compile(r"(?i)\b(azərbaycan|azerbaijan)\b"), "AZ"),
    (re.compile(r"(?i)\b(deutsch|german)\b"), "DE"),
    (re.compile(r"(?i)\b(français|french)\b"), "FR"),
    (re.compile(r"(?i)\b(türk\w*|turkish)\b"), "TR"),
    (re.compile(r"(?i)\b(español|spanish)\b"), "ES"),
    (re.compile(r"(?i)\b(украин\w*|ukrainian)\b"), "UA"),
]

_CODE_TO_LABEL = {
    "EN": "английском (EN, лatinицей)",
    "RU": "русском (RU, кириллица)",
    "AZ": "азербайджанском (AZ, лatinицей)",
    "DE": "немецком (DE)",
    "FR": "французском (FR)",
    "TR": "турецком (TR)",
    "ES": "испанском (ES)",
    "UA": "украинском (UA, кириллица)",
    "UK": "украинском (UA, кириллица)",
}


def detect_languages(label: str, topic: str) -> list[str]:
    text = f"{label} {topic}"
    seen: set[str] = set()
    out: list[str] = []

    def add(code: str) -> None:
        norm = "UA" if code == "UK" else code
        if norm not in seen:
            seen.add(norm)
            out.append(norm)

    for m in _LANG_CODES.finditer(text):
        add(m.group(1).upper())

    for pattern, code in _LANG_NAME_PATTERNS:
        if pattern.search(text):
            add(code)

    return out


def _language_instruction(languages: list[str]) -> str:
    if not languages:
        return (
            "Язык не указан явно. "
            "Все поисковые фразы — только на английском (EN)."
        )
    if len(languages) == 1:
        code = languages[0]
        label = _CODE_TO_LABEL.get(code, code)
        return f"Указан язык: {code}. Все фразы — только на {label}."
    labels = ", ".join(languages)
    details = "; ".join(
        f"{code} — {_CODE_TO_LABEL.get(code, code)}"
        for code in languages
    )
    return (
        f"Указаны языки: {labels}. "
        f"Фразы на КАЖДОМ из них, примерно поровну (не только EN). "
        f"Правила: {details}."
    )


def build_assist_user_message(label: str, topic: str) -> str:
    name = (label or "").strip() or "—"
    desc = (topic or "").strip() or "—"
    msg = (
        f"Вот тебе:\n"
        f"Название базы: {name}\n"
        f"Описание темы: {desc}\n\n"
        f"{_language_instruction(detect_languages(name, desc))}"
    )
    return msg


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
            temperature=0.2,
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
