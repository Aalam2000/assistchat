# src/app/resources/chat_base/export.py
from __future__ import annotations

import re
from typing import Any

_TME_USER = re.compile(
    r"(?:https?://)?(?:t\.me/|telegram\.me/)([A-Za-z0-9_]+)", re.I
)


def _entry_from_item(item: dict[str, Any]) -> str | None:
    eid = str(item.get("external_id") or "").strip()
    if eid:
        return eid
    link = str(item.get("link") or "").strip()
    m = _TME_USER.search(link)
    if m:
        return f"@{m.group(1)}"
    return None


def accepted_whitelist_entries(meta: dict[str, Any]) -> list[str]:
    """Принятые группы/каналы → строки для whitelist PROMPT."""
    items = (meta.get("accepted") or {}).get("telegram") or []
    seen: set[str] = set()
    out: list[str] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        entry = _entry_from_item(raw)
        if not entry:
            continue
        key = entry.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(entry)
    return out
