from collections import deque
from typing import Dict, Deque, List, Literal, Tuple

Role = Literal["user", "assistant"]

# chat_id -> deque[(role, content)]
_store: Dict[int, Deque[Tuple[Role, str]]] = {}

def append(chat_id: int, role: Role, content: str, max_turns: int) -> None:
    """Добавляет реплику и обрезает историю до max_turns пар."""
    dq = _store.setdefault(chat_id, deque())
    dq.append((role, content))
    # Оставляем не больше 2 * max_turns сообщений (user/assistant)
    while len(dq) > max(0, max_turns) * 2:
        dq.popleft()

def get_context(chat_id: int) -> List[dict]:
    """Возвращает историю для OpenAI в формате messages[]."""
    dq = _store.get(chat_id)
    if not dq:
        return []
    return [{"role": r, "content": c} for (r, c) in dq]

def reset(chat_id: int) -> None:
    _store.pop(chat_id, None)
