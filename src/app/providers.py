# src/app/providers.py
from typing import Any, Dict, List, Tuple

# ── хелперы ───────────────────────────────────────────────────────────────────────
def _get(meta: Dict[str, Any] | None, path: str) -> Any:
    cur: Any = meta or {}
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur

def validate_provider_meta(provider: str, meta: Dict[str, Any] | None) -> Tuple[bool, List[str]]:
    """
    Проверяем meta_json по схеме провайдера.
    Возвращаем (ok, issues[]), где issues — коды вида:
     - MISSING:path
     - TYPE:path
     - EMPTY:path
    Для list пустой список допустим. Для str пустая строка — ошибка.
    """
    cfg = PROVIDERS.get(provider)
    if not cfg:
        return False, ["UNKNOWN_PROVIDER"]

    schema: Dict[str, str] = cfg["schema"]
    problems: List[str] = []
    for path, typ in schema.items():
        val = _get(meta, path)
        if val is None:
            problems.append(f"MISSING:{path}")
            continue
        if typ == "str":
            if not isinstance(val, str):
                problems.append(f"TYPE:{path}")
            elif not val.strip():
                problems.append(f"EMPTY:{path}")
        elif typ == "int":
            if not isinstance(val, int):
                problems.append(f"TYPE:{path}")
            elif val <= 0:
                problems.append(f"EMPTY:{path}")
        elif typ == "list":
            if not isinstance(val, list):
                problems.append(f"TYPE:{path}")
        else:
            problems.append(f"SCHEMA:{path}")  # неизвестный тип в схеме
    return (len(problems) == 0), problems

# ── справочник провайдеров ───────────────────────────────────────────────────────
PROVIDERS: Dict[str, Dict[str, Any]] = {
    "telegram": {
        "title": "Telegram",
        "schema": {
            # общие правила/списки — обязательны для всех провайдеров
            "prompts.settings": "str",
            "prompts.rules_common": "str",
            "prompts.rules_dialog": "str",
            "lists.whitelist": "list",
            "lists.blacklist": "list",
            # креды телеграма
            "creds.app_id": "int",
            "creds.app_hash": "str",
            "creds.string_session": "str",
            # полезный атрибут
            "extra.phone_e164": "str",
        },
        "template": {
            "prompts": {"settings": "", "rules_common": "", "rules_dialog": ""},
            "lists": {"whitelist": [], "blacklist": []},
            "creds": {"app_id": 0, "app_hash": "", "string_session": ""},
            "extra": {"phone_e164": ""},
        },
    },
    "avito": {
        "title": "Avito",
        "schema": {
            "prompts.settings": "str",
            "prompts.rules_common": "str",
            "prompts.rules_dialog": "str",
            "lists.whitelist": "list",
            "lists.blacklist": "list",
            "creds.cookie": "str",
            "creds.user_agent": "str",
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
        "schema": {
            "prompts.settings": "str",
            "prompts.rules_common": "str",
            "prompts.rules_dialog": "str",
            "lists.whitelist": "list",
            "lists.blacklist": "list",
            "creds.api_token": "str",
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
        "schema": {
            "prompts.settings": "str",
            "prompts.rules_common": "str",
            "prompts.rules_dialog": "str",
            "lists.whitelist": "list",
            "lists.blacklist": "list",
            # на старте без обязательных creds
        },
        "template": {
            "prompts": {"settings": "", "rules_common": "", "rules_dialog": ""},
            "lists": {"whitelist": [], "blacklist": []},
            "creds": {},
            "extra": {},
        },
    },
}
