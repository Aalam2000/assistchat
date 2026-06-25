# src/app/resources/chat_base/run_control.py
from __future__ import annotations

_running: set[str] = set()
_stop_requested: set[str] = set()


def is_running(resource_id: str) -> bool:
    return str(resource_id) in _running


def is_stop_requested(resource_id: str) -> bool:
    return str(resource_id) in _stop_requested


def mark_running(resource_id: str) -> None:
    _running.add(str(resource_id))


def unmark_running(resource_id: str) -> None:
    _running.discard(str(resource_id))


def request_stop(resource_id: str) -> bool:
    rid = str(resource_id)
    if rid not in _running:
        return False
    _stop_requested.add(rid)
    return True


def clear_stop(resource_id: str) -> None:
    _stop_requested.discard(str(resource_id))
