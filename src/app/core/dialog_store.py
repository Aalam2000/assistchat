"""
src/app/core/dialog_store.py
─────────────────────────────────────────────────────────────────────────────
DB-слой для dialogs/messages.
Здесь нет логики AI: только CRUD/SELECT/INSERT и минимальные инварианты.

Стратегия:
- dialog резолвим по (resource_id, thread_key) -> dialogs.id (UUID).
- историю грузим по messages.dialog_id (последние K*2 сообщений).
- дубль inbound режем уникальностью messages (provider+resource_id+external_chat_id+external_msg_id).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class DialogRow:
    id: UUID
    resource_id: UUID
    thread_key: str
    peer_type: str
    peer_id: int
    chat_id: Optional[int]
    version: int


class DuplicateExternalMessage(Exception):
    """Дубль входящего сообщения (по уникальному ключу внешнего источника)."""


def make_thread_key(*, peer_type: str, peer_id: int, chat_id: Optional[int]) -> str:
    return f"{peer_type}:{int(peer_id)}:{int(chat_id or 0)}"


def get_or_create_dialog(
    db: Session,
    *,
    resource_id: UUID,
    thread_key: str,
    peer_type: str,
    peer_id: int,
    chat_id: Optional[int],
) -> DialogRow:
    """
    Upsert в dialogs по uq(resource_id, thread_key).
    Возвращает DialogRow (id/version).
    """
    q = text(
        """
        INSERT INTO dialogs (resource_id, thread_key, peer_type, peer_id, chat_id)
        VALUES (:resource_id, :thread_key, :peer_type, :peer_id, :chat_id)
        ON CONFLICT (resource_id, thread_key)
        DO UPDATE SET
            peer_type = EXCLUDED.peer_type,
            peer_id   = EXCLUDED.peer_id,
            chat_id   = EXCLUDED.chat_id,
            updated_at = now()
        RETURNING id, resource_id, thread_key, peer_type, peer_id, chat_id, version
        """
    )
    row = db.execute(
        q,
        {
            "resource_id": str(resource_id),
            "thread_key": thread_key,
            "peer_type": peer_type,
            "peer_id": int(peer_id),
            "chat_id": (int(chat_id) if chat_id is not None else None),
        },
    ).mappings().first()

    if not row:
        raise RuntimeError("FAILED_TO_CREATE_DIALOG")

    return DialogRow(
        id=row["id"],
        resource_id=row["resource_id"],
        thread_key=row["thread_key"],
        peer_type=row["peer_type"],
        peer_id=int(row["peer_id"]),
        chat_id=(int(row["chat_id"]) if row["chat_id"] is not None else None),
        version=int(row["version"] or 0),
    )


def load_history(
    db: Session,
    *,
    dialog_id: UUID,
    limit_messages: int,
    exclude_message_id: Optional[UUID] = None,
) -> List[Dict[str, Any]]:
    """
    Возвращает историю в хронологии (старые -> новые).
    Формат: [{"direction":"in|out", "text":"..."}]
    """
    limit_messages = max(0, int(limit_messages))
    if limit_messages == 0:
        return []

    where_excl = ""
    params: Dict[str, Any] = {"dialog_id": str(dialog_id), "lim": limit_messages}
    if exclude_message_id is not None:
        where_excl = "AND id <> :exclude_id"
        params["exclude_id"] = str(exclude_message_id)

    q = text(
        f"""
        SELECT id, direction, text, created_at
        FROM messages
        WHERE dialog_id = :dialog_id
          AND is_internal = false
          AND text IS NOT NULL
          {where_excl}
        ORDER BY created_at DESC
        LIMIT :lim
        """
    )
    rows = list(db.execute(q, params).mappings().all())
    rows.reverse()

    out: List[Dict[str, Any]] = []
    for r in rows:
        txt = (r.get("text") or "").strip()
        if not txt:
            continue
        out.append({"direction": r.get("direction"), "text": txt})
    return out


def insert_message(
    db: Session,
    *,
    resource_id: UUID,
    dialog_id: UUID,
    peer_type: str,
    peer_id: int,
    chat_id: Optional[int],
    direction: str,                 # "in" | "out"
    text_value: str,
    msg_type: str = "text",
    msg_id: Optional[int] = None,
    provider: Optional[str] = None,
    external_chat_id: Optional[str] = None,
    external_msg_id: Optional[str] = None,
    is_internal: bool = False,
    meta_json: Optional[Dict[str, Any]] = None,
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
    latency_ms: Optional[int] = None,
) -> UUID:
    """
    Вставляет строку в messages.
    Возвращает message_id (UUID).

    Если ловим unique-ошибку по external ключам — кидаем DuplicateExternalMessage.
    """
    import uuid

    mid = uuid.uuid4()
    meta_json = meta_json or {}
    meta_s = json.dumps(meta_json, ensure_ascii=False)

    q = text(
        """
        INSERT INTO messages (
            id,
            resource_id,
            dialog_id,
            peer_id,
            peer_type,
            chat_id,
            msg_id,
            direction,
            msg_type,
            text,
            tokens_in,
            tokens_out,
            latency_ms,
            is_internal,
            meta_json,
            provider,
            external_chat_id,
            external_msg_id
        ) VALUES (
            :id,
            :resource_id,
            :dialog_id,
            :peer_id,
            :peer_type,
            :chat_id,
            :msg_id,
            :direction,
            :msg_type,
            :text,
            :tokens_in,
            :tokens_out,
            :latency_ms,
            :is_internal,
            :meta_json::jsonb,
            :provider,
            :external_chat_id,
            :external_msg_id
        )
        """
    )
    try:
        db.execute(
            q,
            {
                "id": str(mid),
                "resource_id": str(resource_id),
                "dialog_id": str(dialog_id),
                "peer_id": int(peer_id),
                "peer_type": peer_type,
                "chat_id": (int(chat_id) if chat_id is not None else None),
                "msg_id": (int(msg_id) if msg_id is not None else None),
                "direction": direction,
                "msg_type": msg_type,
                "text": (text_value or "").strip(),
                "tokens_in": (int(tokens_in) if tokens_in is not None else None),
                "tokens_out": (int(tokens_out) if tokens_out is not None else None),
                "latency_ms": (int(latency_ms) if latency_ms is not None else None),
                "is_internal": bool(is_internal),
                "meta_json": meta_s,
                "provider": provider,
                "external_chat_id": external_chat_id,
                "external_msg_id": external_msg_id,
            },
        )
        return mid
    except IntegrityError as e:
        # Дубль по uq_messages_provider_resource_chat_msg
        raise DuplicateExternalMessage() from e


def touch_dialog(db: Session, *, dialog_id: UUID) -> None:
    db.execute(
        text("UPDATE dialogs SET last_message_at = now(), updated_at = now() WHERE id = :id"),
        {"id": str(dialog_id)},
    )


def bump_graph_state(db: Session, *, dialog_id: UUID, graph_state: Dict[str, Any] | None = None) -> None:
    """
    MVP: можно вообще не менять graph_state (оставлять как есть).
    Но версию диалога мы инкрементим, чтобы было удобно отлаживать.
    """
    state = graph_state or {}
    state_s = json.dumps(state, ensure_ascii=False)
    db.execute(
        text(
            """
            UPDATE dialogs
            SET graph_state = :gs::jsonb,
                version = version + 1,
                updated_at = now()
            WHERE id = :id
            """
        ),
        {"id": str(dialog_id), "gs": state_s},
    )
