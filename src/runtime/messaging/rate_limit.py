import time
from typing import Dict

_last: Dict[int, float] = {}

def allow(chat_id: int, cooldown_sec: int) -> bool:
    """True, если можно отвечать сейчас (кулдаун соблюдён)."""
    now = time.monotonic()
    last = _last.get(chat_id, 0.0)
    if now - last >= max(0, cooldown_sec):
        _last[chat_id] = now
        return True
    return False

def next_allowed_in(chat_id: int, cooldown_sec: int) -> float:
    now = time.monotonic()
    last = _last.get(chat_id, 0.0)
    left = cooldown_sec - (now - last)
    return max(0.0, left)
