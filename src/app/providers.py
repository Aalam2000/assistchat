# src/app/providers.py
from typing import Any, Dict, List, Tuple, Optional

# ── хелперы ───────────────────────────────────────────────────────────────────────
def _get(meta: Dict[str, Any] | None, path: str) -> Any:
    cur: Any = meta or {}
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


# ── нормализация схемы ───────────────────────────────────────────────────────────
# Поддерживаем два формата:
# 1) ЛЕГАСИ: {"path": "str" | "int" | "list"}
# 2) НОВЫЙ: {"version": 1, "groups": [{"title":..., "fields":[{"key": "...", "type": "...", "required": bool, ...}]}]}
#    Типы: string|password|number|textarea|json|list|map|boolean (+ синонимы str/int)
#
# На выходе получаем плоский словарь:
#   { path: {"type": <normalized_type>, "required": <bool>} }
#
def _flatten_schema(schema_obj: Any) -> Dict[str, Dict[str, Any]]:
    flat: Dict[str, Dict[str, Any]] = {}

    # ЛЕГАСИ
    if isinstance(schema_obj, dict) and "groups" not in schema_obj:
        for path, t in schema_obj.items():
            flat[path] = {"type": _normalize_type(t), "required": True}
        return flat

    # НОВЫЙ
    if isinstance(schema_obj, dict) and isinstance(schema_obj.get("groups"), list):
        for grp in schema_obj["groups"]:
            fields = grp.get("fields") or []
            for f in fields:
                path = f.get("key")
                if not path:
                    continue
                t = _normalize_type(f.get("type"))
                required = bool(f.get("required", True))
                flat[path] = {"type": t, "required": required}
        return flat

    # неизвестный формат — возвращаем пусто
    return flat


def _normalize_type(t: Optional[str]) -> str:
    if not t:
        return "string"
    t = t.lower()
    # синонимы
    if t == "str":
        return "string"
    if t == "int":
        return "number"
    # допустимые
    if t in {"string", "password", "number", "textarea", "json", "list", "map", "boolean"}:
        return t
    # дефолт
    return "string"


# ── валидация meta_json по схеме ────────────────────────────────────────────────
def validate_provider_meta(provider: str, meta: Dict[str, Any] | None) -> Tuple[bool, List[str]]:
    """
    Проверяем meta_json по схеме провайдера.
    Возвращаем (ok, issues[]), где issues — коды вида:
      - UNKNOWN_PROVIDER
      - MISSING:path
      - TYPE:path
      - EMPTY:path
      - SCHEMA:path   (неизвестный тип поля в схеме)
    Правила:
      * Для required=False пропускаем MISSING/EMPTY.
      * list может быть пустым без ошибки.
      * textarea/password == string по типу.
      * json → dict, map → dict, boolean → bool, number → int|float (но приводить не пытаемся).
    """
    cfg = PROVIDERS.get(provider)
    if not cfg:
        return False, ["UNKNOWN_PROVIDER"]

    flat = _flatten_schema(cfg.get("schema"))
    problems: List[str] = []

    for path, spec in flat.items():
        typ = spec.get("type") or "string"
        required = bool(spec.get("required", True))

        val = _get(meta, path)

        # отсутствие значения
        if val is None:
            if required:
                problems.append(f"MISSING:{path}")
            continue  # к следующему полю

        # приведение логики required для пустых строк/пустых структур
        if typ in {"string", "password", "textarea"}:
            if not isinstance(val, str):
                problems.append(f"TYPE:{path}")
            else:
                if required and not val.strip():
                    problems.append(f"EMPTY:{path}")

        elif typ == "number":
            if not isinstance(val, (int, float)):
                problems.append(f"TYPE:{path}")

        elif typ == "list":
            if not isinstance(val, list):
                problems.append(f"TYPE:{path}")
            # пустой список допустим даже при required=True

        elif typ in {"json", "map"}:
            if not isinstance(val, dict):
                problems.append(f"TYPE:{path}")
            else:
                if required and len(val) == 0:
                    # для required json/map пустой словарь считаем пустым
                    problems.append(f"EMPTY:{path}")

        elif typ == "boolean":
            if not isinstance(val, bool):
                problems.append(f"TYPE:{path}")

        else:
            problems.append(f"SCHEMA:{path}")  # неизвестный тип в схеме

    return (len(problems) == 0), problems


def get_provider_ui_schema(provider: str) -> Dict[str, Any]:
    """
    Возвращает «расширенную» схему (groups/fields), чтобы UI мог строить форму.
    Если провайдер задан в легаси-формате — оборачиваем в единственную группу.
    """
    cfg = PROVIDERS.get(provider) or {}
    sch = cfg.get("schema")

    # если уже расширенная
    if isinstance(sch, dict) and "groups" in sch:
        return sch

    # легаси → упакуем в одну группу
    flat = _flatten_schema(sch)
    fields = []
    for path, spec in flat.items():
        fields.append({
            "key": path,
            "label": path,
            "type": spec.get("type", "string"),
            "required": bool(spec.get("required", True)),
        })
    return {"version": 1, "groups": [{"title": "Параметры", "fields": fields}]}


# ── справочник провайдеров ───────────────────────────────────────────────────────
# NB: prompts.* помечены как required=False — их заполняем в отдельной модалке.
PROVIDERS: Dict[str, Dict[str, Any]] = {
    "telegram": {
        "title": "Telegram",
        "help": {
            "about": "Подключение Telegram-клиента через Telethon. Можно активировать сразу, если есть string_session.",
            "how_to_get_session": "String Session можно получить во время префлайта или заранее вашим CLI-скриптом.",
        },
        "schema": {
            "version": 1,
            "groups": [
                {
                    "title": "Учетные данные (my.telegram.org)",
                    "fields": [
                        {"key": "creds.app_id", "label": "App ID", "type": "number", "required": True, "placeholder": "123456"},
                        {"key": "creds.app_hash", "label": "App Hash", "type": "password", "required": True, "placeholder": "xxxxxxxxxxxxxxxx"},
                        {"key": "creds.string_session", "label": "String Session", "type": "textarea", "required": False, "help": "Можно оставить пустым и получить в префлайте"},
                        {"key": "extra.phone_e164", "label": "Номер телефона (E.164)", "type": "string", "required": False, "placeholder": "+9945XXXXXXX"},
                    ],
                },
                {
                    "title": "Фильтры доступа",
                    "fields": [
                        {"key": "lists.whitelist", "label": "Whitelist (логины/ID)", "type": "list", "required": False},
                        {"key": "lists.blacklist", "label": "Blacklist (логины/ID)", "type": "list", "required": False},
                        {"key": "extra.allow_groups", "label": "Разрешить группы", "type": "boolean", "required": False},
                    ],
                },
                {
                    "title": "Промпты и правила (заполняются позже во второй модалке)",
                    "fields": [
                        {"key": "prompts.settings", "label": "Настройки", "type": "textarea", "required": False},
                        {"key": "prompts.rules_common", "label": "Общие правила", "type": "textarea", "required": False},
                        {"key": "prompts.rules_dialog", "label": "Правила диалога", "type": "textarea", "required": False},
                    ],
                },
            ],
        },
        "template": {
            "prompts": {"settings": "", "rules_common": "", "rules_dialog": ""},
            "lists": {"whitelist": [], "blacklist": []},
            "creds": {"app_id": 0, "app_hash": "", "string_session": ""},
            "extra": {"phone_e164": "", "allow_groups": True},
        },
    },

    "avito": {
        "title": "Avito",
        "help": {
            "about": "Подключение аккаунта Avito по cookie и user-agent.",
            "cookie": "Укажите валидный cookie (обычно из браузера), следите за сроком жизни.",
        },
        "schema": {
            "version": 1,
            "groups": [
                {
                    "title": "Авторизация",
                    "fields": [
                        {"key": "creds.cookie", "label": "Cookie", "type": "textarea", "required": True},
                        {"key": "creds.user_agent", "label": "User-Agent", "type": "string", "required": True},
                    ],
                },
                {
                    "title": "Фильтры доступа",
                    "fields": [
                        {"key": "lists.whitelist", "label": "Whitelist", "type": "list", "required": False},
                        {"key": "lists.blacklist", "label": "Blacklist", "type": "list", "required": False},
                    ],
                },
                {
                    "title": "Промпты и правила (позже)",
                    "fields": [
                        {"key": "prompts.settings", "label": "Настройки", "type": "textarea", "required": False},
                        {"key": "prompts.rules_common", "label": "Общие правила", "type": "textarea", "required": False},
                        {"key": "prompts.rules_dialog", "label": "Правила диалога", "type": "textarea", "required": False},
                    ],
                },
            ],
        },
        "template": {
            "prompts": {"settings": "", "rules_common": "", "rules_dialog": ""},
            "lists": {"whitelist": [], "blacklist": []},
            "creds": {"cookie": "", "user_agent": ""},
            "extra": {},
        },
    },

    "flru": {
        "title": "FL.ru",
        "help": {
            "about": "Интеграция по API-токену FL.ru.",
        },
        "schema": {
            "version": 1,
            "groups": [
                {
                    "title": "Авторизация",
                    "fields": [
                        {"key": "creds.api_token", "label": "API Token", "type": "password", "required": True},
                    ],
                },
                {
                    "title": "Фильтры доступа",
                    "fields": [
                        {"key": "lists.whitelist", "label": "Whitelist", "type": "list", "required": False},
                        {"key": "lists.blacklist", "label": "Blacklist", "type": "list", "required": False},
                    ],
                },
                {
                    "title": "Промпты и правила (позже)",
                    "fields": [
                        {"key": "prompts.settings", "label": "Настройки", "type": "textarea", "required": False},
                        {"key": "prompts.rules_common", "label": "Общие правила", "type": "textarea", "required": False},
                        {"key": "prompts.rules_dialog", "label": "Правила диалога", "type": "textarea", "required": False},
                    ],
                },
            ],
        },
        "template": {
            "prompts": {"settings": "", "rules_common": "", "rules_dialog": ""},
            "lists": {"whitelist": [], "blacklist": []},
            "creds": {"api_token": ""},
            "extra": {},
        },
    },

    "voice": {
        "title": "Voice",
        "help": {
            "about": "Голосовой чат/колл-центр. На старте без обязательных кредов.",
        },
        "schema": {
            "version": 1,
            "groups": [
                {
                    "title": "Опции",
                    "fields": [
                        {"key": "extra.provider", "label": "Провайдер голоса", "type": "string", "required": False, "placeholder": "whisper/…"},
                        {"key": "extra.lang", "label": "Язык по умолчанию", "type": "string", "required": False, "placeholder": "ru|en|az"},
                    ],
                },
                {
                    "title": "Промпты и правила (позже)",
                    "fields": [
                        {"key": "prompts.settings", "label": "Настройки", "type": "textarea", "required": False},
                        {"key": "prompts.rules_common", "label": "Общие правила", "type": "textarea", "required": False},
                        {"key": "prompts.rules_dialog", "label": "Правила диалога", "type": "textarea", "required": False},
                    ],
                },
                {
                    "title": "Фильтры доступа",
                    "fields": [
                        {"key": "lists.whitelist", "label": "Whitelist", "type": "list", "required": False},
                        {"key": "lists.blacklist", "label": "Blacklist", "type": "list", "required": False},
                    ],
                },
            ],
        },
        "template": {
            "prompts": {"settings": "", "rules_common": "", "rules_dialog": ""},
            "lists": {"whitelist": [], "blacklist": []},
            "creds": {},
            "extra": {"provider": "", "lang": "ru"},
        },
    },
}
