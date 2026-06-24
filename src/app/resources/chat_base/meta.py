# src/app/resources/chat_base/meta.py
from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from typing import Any

MAX_GROUPS_PER_PLATFORM = 200


def default_meta() -> dict[str, Any]:
    return {
        "platform": "telegram",
        "topic": "",
        "queries": [],
        "filters": {
            "min_members": 3000,
            "last_post_max_hours": 24,
        },
        "creds": {
            "app_id": None,
            "app_hash": None,
            "string_session": None,
            "bot_token": None,
        },
        "owner": {
            "telegram_user_id": None,
        },
        "telegram_session_rid": None,
        "blacklist": [],
        "accepted": {
            "telegram": [],
        },
        "pending": {},
        "run": {
            "queries_done": [],
            "last_run_at": None,
            "status": None,
            "message": None,
        },
    }


def normalize_meta(raw: dict[str, Any] | None) -> dict[str, Any]:
    base = default_meta()
    if not isinstance(raw, dict):
        return base
    out = copy.deepcopy(base)
    for key in ("platform", "topic", "telegram_session_rid"):
        if raw.get(key) is not None:
            out[key] = raw[key]
    if isinstance(raw.get("queries"), list):
        out["queries"] = [
            str(q).strip() for q in raw["queries"] if str(q).strip()
        ]
    if isinstance(raw.get("filters"), dict):
        out["filters"].update(raw["filters"])
    if isinstance(raw.get("creds"), dict):
        out["creds"].update(raw["creds"])
    if isinstance(raw.get("owner"), dict):
        out["owner"].update(raw["owner"])
    if isinstance(raw.get("blacklist"), list):
        out["blacklist"] = [str(x) for x in raw["blacklist"] if x]
    if isinstance(raw.get("accepted"), dict):
        for plat, items in raw["accepted"].items():
            if isinstance(items, list):
                out["accepted"][plat] = items
    if isinstance(raw.get("pending"), dict):
        out["pending"] = raw["pending"]
    if isinstance(raw.get("run"), dict):
        out["run"].update(raw["run"])
    return out


def external_id(username: str | None, chat_id: int | None) -> str:
    if username:
        u = username.strip().lstrip("@")
        return f"@{u}" if u else str(chat_id or "")
    return str(chat_id or "")


def is_blocked(
    meta: dict[str, Any], eid: str, platform: str = "telegram"
) -> bool:
    if eid in (meta.get("blacklist") or []):
        return True
    accepted = (meta.get("accepted") or {}).get(platform) or []
    return any(str(x.get("external_id")) == eid for x in accepted)


def accepted_count(meta: dict[str, Any], platform: str = "telegram") -> int:
    return len((meta.get("accepted") or {}).get(platform) or [])


def can_accept_more(meta: dict[str, Any], platform: str = "telegram") -> bool:
    return accepted_count(meta, platform) < MAX_GROUPS_PER_PLATFORM


def add_pending(meta: dict[str, Any], candidate: dict[str, Any]) -> str:
    pid = uuid.uuid4().hex[:12]
    pending = dict(meta.get("pending") or {})
    pending[pid] = candidate
    meta["pending"] = pending
    return pid


def resolve_pending(
    meta: dict[str, Any], pending_id: str
) -> dict[str, Any] | None:
    pending = dict(meta.get("pending") or {})
    item = pending.pop(pending_id, None)
    meta["pending"] = pending
    return item


def accept_candidate(
    meta: dict[str, Any],
    candidate: dict[str, Any],
    platform: str = "telegram",
) -> bool:
    if not can_accept_more(meta, platform):
        return False
    eid = candidate.get("external_id")
    if not eid or is_blocked(meta, eid, platform):
        return False
    accepted = list((meta.get("accepted") or {}).get(platform) or [])
    candidate = dict(candidate)
    candidate["accepted_at"] = datetime.now(timezone.utc).isoformat()
    accepted.append(candidate)
    meta.setdefault("accepted", {})[platform] = accepted
    return True


def reject_candidate(meta: dict[str, Any], candidate: dict[str, Any]) -> None:
    eid = candidate.get("external_id")
    if not eid:
        return
    bl = list(meta.get("blacklist") or [])
    if eid not in bl:
        bl.append(eid)
    meta["blacklist"] = bl


def suggest_queries(topic: str) -> list[str]:
    t = (topic or "").strip()
    if not t:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for q in (
        t,
        f"{t} jobs",
        f"{t} freelance",
        f"{t} work",
        f"работа {t}",
        f"заказы {t}",
    ):
        q = q.strip()
        if q and q.lower() not in seen:
            seen.add(q.lower())
            out.append(q)
    return out
