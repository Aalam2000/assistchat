# src/app/resources/chat_base/callback_data.py
from __future__ import annotations

MAX_CALLBACK_DATA = 64


def build_callback_data(
    action: str, chat_base_rid: str, pending_id: str
) -> str:
    data = f"cb:{action}:{chat_base_rid}:{pending_id}"
    if len(data) > MAX_CALLBACK_DATA:
        raise ValueError("callback_data too long")
    return data


def parse_callback_data(data: str) -> tuple[str, str, str] | None:
    parts = (data or "").split(":")
    if len(parts) != 4 or parts[0] != "cb":
        return None
    action, cb_rid, pending_id = parts[1], parts[2], parts[3]
    if action not in ("a", "s") or not cb_rid or not pending_id:
        return None
    return action, cb_rid, pending_id


def parse_callback_data_legacy(data: str) -> tuple[str, str] | None:
    """Старые карточки: cb:a:{pending_id} без rid базы."""
    parts = (data or "").split(":")
    if len(parts) != 3 or parts[0] != "cb":
        return None
    action, pending_id = parts[1], parts[2]
    if action not in ("a", "s") or not pending_id:
        return None
    return action, pending_id
