"""
src/app/core/dialog_graph.py
────────────────────────────────────────────────────────────
ТОЛЬКО "LangGraph-слой" (без БД, без ключей, без HTTP).

Задача:
- принять (prompt + drive_context + history + user_text + state)
- подготовить пакет для AI (messages + meta)
- принять ответ AI и обновить state (graph_state)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class AIRequest:
    """Готовый пакет для AI-транспорта (только то, что отправляем)."""
    messages: List[Dict[str, str]]           # [{"role":"system|user|assistant","content":"..."}]
    meta: Dict[str, Any]                     # служебные метки (для логов)


@dataclass(frozen=True)
class AIResponse:
    """Нормализованный ответ от AI-транспорта (то, что получили)."""
    text: str
    usage: Dict[str, Any]                    # {"total_tokens":..., ...}
    raw: Optional[Dict[str, Any]] = None     # по желанию


def build_request(
    *,
    thread_id: str,
    user_text: str,
    system_prompt: str,
    drive_context: str,
    history: List[Dict[str, str]],
    state: Dict[str, Any],
) -> AIRequest:
    """
    Формируем messages для AI.

    Важно:
    - history уже должен быть обрезан снаружи (по PROMPT.history_pairs).
    - здесь нет никакой БД/телеги/ключей.
    """
    user_text = (user_text or "").strip()
    if not user_text:
        return AIRequest(messages=[], meta={"thread_id": thread_id, "skip": "EMPTY_USER_TEXT"})

    sys = (system_prompt or "").strip()
    if drive_context:
        drive_context = (drive_context or "").strip()
        if drive_context:
            sys = (sys + "\n\n" if sys else "") + "KNOWLEDGE:\n" + drive_context

    messages: List[Dict[str, str]] = []
    if sys:
        messages.append({"role": "system", "content": sys})

    # history (ожидаем уже в формате role/content)
    for m in history or []:
        role = (m.get("role") or "").strip()
        content = (m.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_text})

    meta = {
        "thread_id": thread_id,
        "history_count": len(history or []),
        "turn": int((state or {}).get("turn", 0)) + 1,
    }
    return AIRequest(messages=messages, meta=meta)


def apply_response(
    *,
    state: Dict[str, Any],
    request_meta: Dict[str, Any],
    ai_response: AIResponse,
) -> tuple[str, Dict[str, Any], Dict[str, Any]]:
    """
    Разбор ответа AI + обновление state (graph_state).
    """
    txt = (ai_response.text or "").strip()
    new_state = dict(state or {})
    new_state["turn"] = int(request_meta.get("turn") or new_state.get("turn") or 0)
    if txt:
        new_state["last_answer"] = txt

    meta = {
        "graph": {
            "turn": new_state.get("turn"),
            "thread_id": request_meta.get("thread_id"),
        },
        "usage": ai_response.usage or {},
    }
    return txt, new_state, meta
