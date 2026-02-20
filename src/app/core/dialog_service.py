"""
src/app/core/dialog_service.py
────────────────────────────────────────────────────────────
ОРКЕСТРАТОР (БД + последовательность + вызов graph + вызов transport).

Задача:
- get_or_create dialogs
- запрет параллельной обработки в одном dialog (pg_advisory_xact_lock)
- дедуп входящих (уникальность messages)
- load prompt + load api_keys + выбрать провайдера/ключ/модель
- history -> dialog_graph.build_request -> ai_transport.chat -> dialog_graph.apply_response
- записать messages(out) + обновить dialogs.graph_state/version/last_message_at + usage_today
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.app.core.db import SessionLocal
from src.models.resource import Resource

from src.app.core.dialog_graph import AIResponse, apply_response, build_request
from src.app.core.ai_transport import AIChatConfig, chat, provider_from_key_field


# ────────────────────────────────────────────────────────────────
# helpers
# ────────────────────────────────────────────────────────────────

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _json(obj: Any) -> str:
    return json.dumps(obj or {}, ensure_ascii=False)


def _dot_get(meta: Dict[str, Any] | None, path: str) -> Any:
    cur: Any = meta or {}
    for k in (path or "").split("."):
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def _uuid(v: Any) -> Optional[uuid.UUID]:
    if not v:
        return None
    if isinstance(v, uuid.UUID):
        return v
    try:
        return uuid.UUID(str(v))
    except Exception:
        return None


def _uuid_to_pg_lock_key(u: uuid.UUID) -> int:
    # 64-bit signed
    key = (u.int >> 64) & ((1 << 64) - 1)
    if key >= (1 << 63):
        key -= (1 << 64)
    return int(key)


def _rows_to_history(rows: List[Tuple[str, str]]) -> List[Dict[str, str]]:
    hist: List[Dict[str, str]] = []
    for direction, txt in rows:
        t = (txt or "").strip()
        if not t:
            continue
        role = "user" if direction == "in" else "assistant"
        if hist and hist[-1]["content"] == t:
            continue
        hist.append({"role": role, "content": t})
    return hist


# ────────────────────────────────────────────────────────────────
# SQL
# ────────────────────────────────────────────────────────────────

_SQL_GET_OR_CREATE_DIALOG = text("""
INSERT INTO dialogs (resource_id, thread_key, peer_type, peer_id, chat_id)
VALUES (:resource_id, :thread_key, :peer_type, :peer_id, :chat_id)
ON CONFLICT (resource_id, thread_key)
DO UPDATE SET updated_at = now()
RETURNING id, graph_state, version;
""")

_SQL_LOCK_DIALOG = text("SELECT pg_advisory_xact_lock(:key);")

_SQL_INSERT_MESSAGE = text("""
INSERT INTO messages (
  id, resource_id, dialog_id,
  peer_id, peer_type, chat_id, msg_id,
  direction, msg_type, text,
  tokens_in, tokens_out, latency_ms,
  provider, external_chat_id, external_msg_id,
  is_internal, meta_json, created_at
)
VALUES (
  :id, :resource_id, :dialog_id,
  :peer_id, :peer_type, :chat_id, :msg_id,
  :direction, :msg_type, :text,
  :tokens_in, :tokens_out, :latency_ms,
  :provider, :external_chat_id, :external_msg_id,
  :is_internal, CAST(:meta_json AS jsonb), now()
)
ON CONFLICT ON CONSTRAINT uq_messages_provider_resource_chat_msg
DO NOTHING
RETURNING id;
""")

_SQL_LOAD_HISTORY = text("""
SELECT direction, text
FROM messages
WHERE dialog_id = :dialog_id
  AND is_internal = false
  AND text IS NOT NULL
  AND length(text) > 0
ORDER BY created_at DESC
LIMIT :limit;
""")

_SQL_UPDATE_DIALOG = text("""
UPDATE dialogs
SET graph_state = CAST(:graph_state AS jsonb),
    last_message_at = :ts,
    updated_at = now(),
    version = version + 1
WHERE id = :dialog_id;
""")

_SQL_UPDATE_RESOURCE_USAGE = text("""
UPDATE resources
SET usage_today = usage_today + :tokens,
    last_activity = :ts,
    updated_at = now()
WHERE id = :resource_id;
""")

_SQL_ATTACH_OUT_IDS = text("""
UPDATE messages
SET msg_id = COALESCE(:msg_id, msg_id),
    external_msg_id = COALESCE(:external_msg_id, external_msg_id)
WHERE id = :message_id;
""")



# ────────────────────────────────────────────────────────────────
# PROMPT parsing (минимально, без магии)
# ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PromptRuntime:
    system_prompt: str
    history_pairs: int
    google_source: str


def _parse_prompt_resource(prompt_res: Resource) -> PromptRuntime:
    meta = prompt_res.meta_json or {}
    p = meta.get("prompt") if isinstance(meta.get("prompt"), dict) else meta

    system_prompt = (p.get("system_prompt") or "").strip()
    google_source = (p.get("google_source") or "").strip()

    # важно: history_pairs живёт в PROMPT
    hp = p.get("history_pairs")
    try:
        history_pairs = max(0, int(hp if hp is not None else 20))
    except Exception:
        history_pairs = 20

    return PromptRuntime(system_prompt=system_prompt, history_pairs=history_pairs, google_source=google_source)


# ────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────

async def process_incoming(
    *,
    resource_id: str | uuid.UUID,
    provider: str,
    peer_type: str,
    peer_id: int,
    chat_id: Optional[int],
    external_chat_id: str,
    external_msg_id: str,
    msg_id: Optional[int] = None,
    text_value: str = "",
    drive_context: str = "",           # пока пусто, RAG добавим позже
    model_text: Optional[str] = None,  # модель выбирается в ресурсе-транспорте (Telegram), но ядро её применяет
    temperature: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """
    Возвращает:
      {"text": "...", "dialog_id": "...", "out_message_id": "...", "meta": {...}}
    или None (если дубль/пусто).
    """
    rid = _uuid(resource_id)
    if not rid:
        raise ValueError("BAD_RESOURCE_ID")

    provider = (provider or "").strip() or "unknown"
    peer_type = (peer_type or "").strip() or "unknown"
    external_chat_id = (external_chat_id or "").strip()
    external_msg_id = (external_msg_id or "").strip()
    if not external_chat_id or not external_msg_id:
        raise ValueError("MISSING_EXTERNAL_IDS")

    # thread_key: стабильно идентифицирует диалог внутри ресурса
    thread_key = f"{provider}:{external_chat_id}"

    # 1) загрузим ресурс (вне транзакции)
    def _load_resource_sync() -> Resource:
        db = SessionLocal()
        try:
            r = db.get(Resource, rid)
            if not r:
                raise RuntimeError("RESOURCE_NOT_FOUND")
            if (r.status or "") != "active":
                raise RuntimeError("RESOURCE_NOT_ACTIVE")
            return r
        finally:
            db.close()

    resource = await asyncio.to_thread(_load_resource_sync)
    meta = resource.meta_json or {}

    # 2) резолвим обязательные связи из resource.meta_json
    # TG router хранит плоско: prompt_id / ai_keys_resource_id / ai_key_field / model
    # Поддержим и новый формат ai.* (на будущее)
    prompt_id = _uuid(meta.get("prompt_id") or _dot_get(meta, "prompt_id"))

    ai_keys_id = _uuid(
        _dot_get(meta, "ai.api_keys_resource_id")
        or meta.get("ai_keys_resource_id")
    )
    ai_key_field = (
            _dot_get(meta, "ai.api_key_field")
            or meta.get("ai_key_field")
            or ""
    ).strip()

    if not prompt_id:
        raise RuntimeError("PROMPT_NOT_SET_IN_RESOURCE")
    if not ai_keys_id or not ai_key_field:
        raise RuntimeError("AI_KEYS_NOT_SET_IN_RESOURCE")

    model = (
            model_text
            or _dot_get(meta, "ai.model_text")
            or _dot_get(meta, "ai.model")
            or meta.get("model")
            or meta.get("model_text")
            or ""
    ).strip()
    if not model:
        raise RuntimeError("MODEL_NOT_SET_IN_RESOURCE")

    if temperature is None:
        raw_t = _dot_get(meta, "ai.temperature")
        if raw_t is None:
            raw_t = meta.get("temperature")
        try:
            temperature = float(raw_t if raw_t is not None else 0.7)
        except Exception:
            temperature = 0.7

    # 3) транзакция: dialog + lock + дедуп + история + запись out
    def _tx_sync() -> Optional[Dict[str, Any]]:
        db: Session = SessionLocal()
        t0 = time.perf_counter()
        try:
            # 3.1 get_or_create dialog
            row = db.execute(_SQL_GET_OR_CREATE_DIALOG, {
                "resource_id": str(rid),
                "thread_key": thread_key,
                "peer_type": peer_type,
                "peer_id": int(peer_id),
                "chat_id": int(chat_id) if chat_id is not None else None,
            }).first()
            dialog_id = uuid.UUID(str(row[0]))
            graph_state = row[1] or {}
            lock_key = _uuid_to_pg_lock_key(dialog_id)

            # 3.2 запрет параллели в одном диалоге (на всю транзакцию)
            db.execute(_SQL_LOCK_DIALOG, {"key": lock_key})

            # 3.3 дедуп/запись IN
            in_id = uuid.uuid4()
            inserted_in = db.execute(_SQL_INSERT_MESSAGE, {
                "id": str(in_id),
                "resource_id": str(rid),
                "dialog_id": str(dialog_id),
                "peer_id": int(peer_id),
                "peer_type": peer_type,
                "chat_id": int(chat_id) if chat_id is not None else None,
                "msg_id": int(msg_id) if msg_id is not None else None,
                "direction": "in",
                "msg_type": "text",
                "text": (text_value or "").strip() or None,
                "tokens_in": None,
                "tokens_out": None,
                "latency_ms": None,
                "provider": provider,
                "external_chat_id": external_chat_id,
                "external_msg_id": external_msg_id,
                "is_internal": False,
                "meta_json": _json({"phase": "incoming"}),
            }).scalar_one_or_none()
            if not inserted_in:
                db.commit()
                return None  # дубль

            user_text = (text_value or "").strip()
            if not user_text:
                db.commit()
                return None

            # 3.4 load prompt + api_keys
            prompt_res = db.get(Resource, prompt_id)
            keys_res = db.get(Resource, ai_keys_id)
            if not prompt_res or prompt_res.provider != "prompt":
                raise RuntimeError("PROMPT_RESOURCE_NOT_FOUND")
            if not keys_res or keys_res.provider != "api_keys":
                raise RuntimeError("API_KEYS_RESOURCE_NOT_FOUND")

            prompt_rt = _parse_prompt_resource(prompt_res)

            keys_meta = keys_res.meta_json or {}
            api_key_val = (_dot_get(keys_meta, ai_key_field) or "").strip()
            if not api_key_val:
                raise RuntimeError("API_KEY_FIELD_EMPTY")

            # 3.5 history (limit из PROMPT)
            limit_msgs = int(prompt_rt.history_pairs) * 2
            rows = db.execute(_SQL_LOAD_HISTORY, {"dialog_id": str(dialog_id), "limit": limit_msgs}).all()
            rows = list(rows)
            rows.reverse()
            history = _rows_to_history([(r[0], r[1]) for r in rows])

            # 3.6 graph -> request
            thread_id = f"{provider}:{rid}:{dialog_id}"
            req = build_request(
                thread_id=thread_id,
                user_text=user_text,
                system_prompt=prompt_rt.system_prompt,
                drive_context=drive_context,
                history=history,
                state=graph_state or {},
            )
            if not req.messages:
                db.commit()
                return None

            # 3.7 transport chat (внутри tx нельзя await; выйдем наружу)
            db.commit()
            # вернём всё, что нужно для async части
            return {
                "dialog_id": dialog_id,
                "graph_state": graph_state or {},
                "req_messages": req.messages,
                "req_meta": req.meta,
                "api_key": api_key_val,
                "key_field": ai_key_field,
                "model": model,
                "temperature": float(temperature or 0.7),
                "prompt_google_source": prompt_rt.google_source,
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    prepared = await asyncio.to_thread(_tx_sync)
    if prepared is None:
        return None

    # 4) async вызов AI (вне DB tx)
    prov = provider_from_key_field(prepared["key_field"])
    result = await chat(
        cfg=AIChatConfig(
            provider=prov,
            api_key=prepared["api_key"],
            model=prepared["model"],
            temperature=prepared["temperature"],
        ),
        messages=prepared["req_messages"],
    )

    if not result.ok:
        answer_text = f"⚠️ AI error: {result.error}"
        usage = result.usage or {"provider": prov.value, "model": prepared["model"]}
    else:
        answer_text = (result.text or "").strip()
        usage = result.usage or {}

    # 5) apply graph (обновляем graph_state)
    answer_text, new_state, graph_meta = apply_response(
        state=prepared["graph_state"],
        request_meta=prepared["req_meta"],
        ai_response=AIResponse(text=answer_text, usage=usage, raw=result.raw),
    )

    # 6) записываем OUT + update dialogs + usage
    def _tx_save_out_sync() -> Dict[str, Any]:
        db: Session = SessionLocal()
        t0 = time.perf_counter()
        try:
            dialog_id = prepared["dialog_id"]
            lock_key = _uuid_to_pg_lock_key(dialog_id)
            db.execute(_SQL_LOCK_DIALOG, {"key": lock_key})

            out_id = uuid.uuid4()
            latency_ms = int((time.perf_counter() - t0) * 1000)

            out_meta = {
                "phase": "outgoing",
                "prompt_google_source": prepared["prompt_google_source"],
                "provider": prov.value,
                "model": prepared["model"],
                "usage": usage,
                "graph": graph_meta.get("graph") if isinstance(graph_meta, dict) else {},
            }

            db.execute(_SQL_INSERT_MESSAGE, {
                "id": str(out_id),
                "resource_id": str(rid),
                "dialog_id": str(dialog_id),
                "peer_id": int(peer_id),
                "peer_type": peer_type,
                "chat_id": int(chat_id) if chat_id is not None else None,
                "msg_id": None,
                "direction": "out",
                "msg_type": "text",
                "text": answer_text,
                "tokens_in": None,
                "tokens_out": int(usage.get("total_tokens") or 0),
                "latency_ms": latency_ms,
                "provider": provider,
                "external_chat_id": external_chat_id,
                "external_msg_id": None,  # проставит транспорт после отправки (если надо)
                "is_internal": False,
                "meta_json": _json(out_meta),
            })

            ts = _now_utc()
            db.execute(_SQL_UPDATE_DIALOG, {
                "dialog_id": str(dialog_id),
                "graph_state": _json(new_state),
                "ts": ts,
            })
            db.execute(_SQL_UPDATE_RESOURCE_USAGE, {
                "resource_id": str(rid),
                "tokens": int(usage.get("total_tokens") or 0),
                "ts": ts,
            })

            db.commit()
            return {
                "text": answer_text,
                "dialog_id": str(dialog_id),
                "out_message_id": str(out_id),
                "meta": out_meta,
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    return await asyncio.to_thread(_tx_save_out_sync)


async def attach_outgoing_ids(
    *,
    message_id: str | uuid.UUID,
    msg_id: Optional[int],
    external_msg_id: Optional[str],
) -> None:
    mid = _uuid(message_id)
    if not mid:
        raise ValueError("BAD_MESSAGE_ID")

    def _sync():
        db = SessionLocal()
        try:
            db.execute(_SQL_ATTACH_OUT_IDS, {
                "message_id": str(mid),
                "msg_id": int(msg_id) if msg_id is not None else None,
                "external_msg_id": (external_msg_id or None),
            })
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    await asyncio.to_thread(_sync)
