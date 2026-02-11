"""
src/app/core/dialog_graph.py
─────────────────────────────────────────────────────────────────────────────
Общий модуль диалогов для всей платформы.

Цель:
- Единая точка входа для "ведения диалога" (контекст/история/промпт/вызов AI).
- Telegram (и другие ресурсы) остаются адаптерами транспорта: receive/send/rules/session.
- Ключ/модель НЕ добываются здесь: ядро получает уже "разрешённый" ai_client
  (ключ/модель резолвит текущий активный ресурс, например Telegram).

LangGraph:
- В этом файле предусмотрены точки расширения (backend="langgraph") и каркас под graph/checkpointer.
- По умолчанию работает backend="basic" (прямой вызов ai_client).
"""

from __future__ import annotations

import os
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.app.core.db import SessionLocal
from src.models.message import Message
from src.models.resource import Resource


# ────────────────────────────────────────────────────────────────
# Конфиг графа (точка будущей настройки LangGraph)
# ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DialogGraphConfig:
    """
    engine:
      - "basic"    : прямой вызов ai_client (сегодня)
      - "langgraph": LangGraph backend (добавим позже, когда согласуем каркас/память/чекпоинтер)
    """
    engine: str = "basic"

    @staticmethod
    def from_env() -> "DialogGraphConfig":
        return DialogGraphConfig(engine=(os.getenv("DIALOG_ENGINE", "basic") or "basic").strip().lower())


@dataclass
class DialogResult:
    text: str
    tokens: int = 0
    mode: str = "text"          # text|voice|none
    audio_bytes: Optional[bytes] = None
    meta: Dict[str, Any] = None


# ────────────────────────────────────────────────────────────────
# Вспомогательные функции (общие)
# ────────────────────────────────────────────────────────────────

def _compose_system_prompt(resource: Resource) -> str:
    prompts = (resource.meta_json or {}).get("prompts", {}) or {}
    return "\n".join(
        filter(None, [
            (prompts.get("settings") or "").strip(),
            (prompts.get("rules_common") or "").strip(),
            (prompts.get("rules_dialog") or "").strip(),
        ])
    ).strip()


def _history_limit(resource: Resource, override: Optional[int] = None) -> int:
    if override is not None:
        try:
            return max(0, int(override))
        except Exception:
            return 20
    try:
        return int((resource.meta_json or {}).get("limits", {}).get("history_length", 20))
    except Exception:
        return 20


def _rows_to_context(rows: List[Message]) -> List[Dict[str, Any]]:
    """
    Приводим Message -> формат сообщений для LLM:
      {"role":"user|assistant", "content":"..."}
    + защита от дублей подряд.
    """
    ctx: List[Dict[str, Any]] = []
    for m in rows:
        if not m.text:
            continue
        role = "user" if m.direction == "in" else "assistant"
        content = (m.text or "").strip()
        if not content:
            continue
        if ctx and ctx[-1].get("content") == content:
            continue
        ctx.append({"role": role, "content": content})
    return ctx


# ────────────────────────────────────────────────────────────────
# DB helpers (SYNC) — вызываем через asyncio.to_thread, чтобы не блокировать event loop
# ────────────────────────────────────────────────────────────────

def _db_load_history(resource_id, peer_id: int, limit: int) -> List[Message]:
    db: Session = SessionLocal()
    try:
        rows = (
            db.execute(
                select(Message)
                .where(Message.resource_id == resource_id, Message.peer_id == peer_id)
                .order_by(Message.created_at.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        rows = list(rows)
        rows.reverse()  # в хронологию
        return rows
    finally:
        db.close()


def _db_update_usage(resource_id, tokens: int) -> None:
    db: Session = SessionLocal()
    try:
        r = db.get(Resource, resource_id)
        if not r:
            return
        r.last_activity = datetime.now(timezone.utc)
        r.usage_today = (r.usage_today or 0) + int(tokens or 0)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


# ────────────────────────────────────────────────────────────────
# Backends (точка расширения под LangGraph)
# ────────────────────────────────────────────────────────────────

class DialogBackend(Protocol):
    async def run(
        self,
        *,
        text: str,
        audio_bytes: Optional[bytes],
        prefer_voice_reply: bool,
        system_prompt: str,
        context: List[Dict[str, Any]],
        ai_client: Any,
        thread_id: str,
    ) -> DialogResult: ...


class BasicBackend:
    """
    Сегодняшний backend: прямой вызов ai_client.
    Требование: ai_client должен уметь либо handle_message(...), либо reply_text(...).
    """

    async def run(
        self,
        *,
        text: str,
        audio_bytes: Optional[bytes],
        prefer_voice_reply: bool,
        system_prompt: str,
        context: List[Dict[str, Any]],
        ai_client: Any,
        thread_id: str,
    ) -> DialogResult:
        # Универсальный путь: если клиент поддерживает handle_message — используем.
        if hasattr(ai_client, "handle_message"):
            res = await ai_client.handle_message(
                text=text,
                audio_bytes=audio_bytes,
                prefer_voice_reply=prefer_voice_reply,
                system_prompt=system_prompt,
                context=context,
            )
            res = res or {}
            return DialogResult(
                text=(res.get("text") or "").strip(),
                tokens=int(res.get("tokens") or 0),
                mode=(res.get("mode") or "text"),
                audio_bytes=res.get("audio_bytes"),
                meta={"thread_id": thread_id, "backend": "basic"},
            )

        # Фолбэк: только текст
        if hasattr(ai_client, "reply_text"):
            reply_text, tokens = await ai_client.reply_text(
                prompt=text,
                system_prompt=system_prompt,
                context=context,
            )
            return DialogResult(
                text=(reply_text or "").strip(),
                tokens=int(tokens or 0),
                mode="text",
                audio_bytes=None,
                meta={"thread_id": thread_id, "backend": "basic"},
            )

        raise RuntimeError("ai_client has no supported methods (expected handle_message or reply_text)")


class LangGraphBackend:
    """
    Каркас под LangGraph.
    Сейчас — заглушка. Когда согласуем:
      - state schema
      - checkpointer (Postgres/Redis)
      - memory policy (summary+lastK+rag)
    сюда подключим реальный граф и будем вызывать его из run().

    Важно: этот backend не должен знать про Telegram.
    """

    def __init__(self, cfg: DialogGraphConfig):
        self.cfg = cfg
        # TODO(LANGGRAPH): здесь будет build_graph(cfg) + init checkpointer/store.
        # self.graph = build_langgraph_graph(cfg)

    async def run(
        self,
        *,
        text: str,
        audio_bytes: Optional[bytes],
        prefer_voice_reply: bool,
        system_prompt: str,
        context: List[Dict[str, Any]],
        ai_client: Any,
        thread_id: str,
    ) -> DialogResult:
        # TODO(LANGGRAPH): здесь будет:
        #  1) load_state(thread_id)
        #  2) graph.invoke(...) / graph.ainvoke(...)
        #  3) save_state(thread_id)
        # Пока явно падаем, чтобы никто случайно не включил env DIALOG_ENGINE=langgraph без реализации.
        raise NotImplementedError("LangGraph backend is not implemented yet")


def _select_backend(cfg: DialogGraphConfig) -> DialogBackend:
    if cfg.engine == "langgraph":
        return LangGraphBackend(cfg)
    return BasicBackend()


# ────────────────────────────────────────────────────────────────
# Единая точка входа (v1)
# ────────────────────────────────────────────────────────────────

async def dialog_graph_v1(
    *,
    resource: Resource,
    peer_id: int,
    text: str = "",
    audio_bytes: Optional[bytes] = None,
    prefer_voice_reply: bool = False,
    ai_client: Any,
    cfg: Optional[DialogGraphConfig] = None,
    history_limit: Optional[int] = None,
    system_prompt_override: Optional[str] = None,
    update_usage: bool = True,
) -> Optional[DialogResult]:
    """
    Общий диалоговый runtime.

    Вход:
      - resource: текущий активный ресурс (например telegram resource)
      - peer_id : идентификатор собеседника/чата (для истории)
      - text/audio_bytes: вход пользователя
      - ai_client: уже подготовленный клиент (ключ/модель взяты из resource meta)
    Выход:
      - DialogResult или None (если нет текста)
    """

    if ai_client is None:
        raise ValueError("ai_client is required (must be resolved by the active resource)")

    # thread_id — общий ключ диалога для будущей персистентной памяти LangGraph
    thread_id = f"{resource.provider}:{resource.id}:{peer_id}"

    # Если текста нет, но есть аудио — попробуем распознать (если клиент умеет)
    src_text = (text or "").strip()
    if not src_text and audio_bytes and hasattr(ai_client, "transcribe_audio"):
        try:
            src_text = (await ai_client.transcribe_audio(audio_bytes)) or ""
            src_text = src_text.strip()
        except Exception:
            src_text = ""

    if not src_text:
        return None

    # История (DB) — в отдельном потоке
    limit = _history_limit(resource, history_limit)
    rows = await asyncio.to_thread(_db_load_history, resource.id, int(peer_id), int(limit))
    context = _rows_to_context(rows)

    # Системный промпт
    system_prompt = (system_prompt_override or "").strip() or _compose_system_prompt(resource)

    # Выбор backend (basic/langgraph)
    cfg = cfg or DialogGraphConfig.from_env()
    backend = _select_backend(cfg)

    # Запуск
    result = await backend.run(
        text=src_text,
        audio_bytes=audio_bytes,
        prefer_voice_reply=prefer_voice_reply,
        system_prompt=system_prompt,
        context=context,
        ai_client=ai_client,
        thread_id=thread_id,
    )

    # Учёт usage/last_activity (общий минимум)
    if update_usage:
        try:
            await asyncio.to_thread(_db_update_usage, resource.id, int(result.tokens or 0))
        except Exception:
            pass

    return result
