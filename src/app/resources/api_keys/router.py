# src/app/resources/api_keys/router.py
from __future__ import annotations

from uuid import UUID
from datetime import datetime, timezone

import requests
from fastapi import APIRouter, Depends, Form, HTTPException, Body
from sqlalchemy.orm import Session as SASession

from src.app.core.auth import get_current_user
from src.app.core.db import get_db
from src.models.resource import Resource

router = APIRouter(prefix="/api/api_keys", tags=["api_keys"])


@router.post("/create")
async def create_api_keys_resource(
    label: str = Form(...),
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    r = Resource(
        provider="api_keys",
        user_id=user.id,
        label=(label or "").strip() or "API keys",
        status="new",
        meta_json={"creds": {}, "phase": "new", "error": None, "verified": {}},
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"ok": True, "id": r.id}


@router.put("/{rid}")
async def save_api_keys_resource(
    rid: str,
    payload: dict = Body(...),
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    try:
        rid_uuid = UUID(str(rid))
    except Exception:
        raise HTTPException(status_code=400, detail="BAD_ID")

    row = db.query(Resource).filter(Resource.id == rid_uuid).first()
    if not row:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    if row.user_id != user.id:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    if row.provider != "api_keys":
        raise HTTPException(status_code=400, detail="BAD_PROVIDER")

    label = (payload.get("label") or "").strip() or row.label or "API keys"
    meta_json = payload.get("meta_json")
    if meta_json is None or not isinstance(meta_json, dict):
        meta_json = row.meta_json or {}

    # NOTE: обычный save НЕ делает валидацию и НЕ гарантирует сохранение только валидных.
    # Валидные ключи фиксируются через /verify.
    row.label = label
    row.meta_json = meta_json

    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "id": str(row.id)}


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _req_ok(method: str, url: str, headers: dict, timeout: float = 10.0) -> tuple[bool, str | None]:
    try:
        r = requests.request(method, url, headers=headers, timeout=timeout)
        if 200 <= r.status_code < 300:
            return True, None
        # коротко, без тела (чтобы не утечь секретами/диагностикой)
        return False, f"HTTP_{r.status_code}"
    except Exception as e:
        return False, e.__class__.__name__


def _verify_key(key_name: str, value: str) -> tuple[bool, str | None]:
    """
    key_name: "creds.openai_api_key" и т.п.
    """
    v = (value or "").strip()
    if not v:
        return False, "EMPTY"

    # OpenAI обычный ключ
    if key_name == "creds.openai_api_key":
        return _req_ok("GET", "https://api.openai.com/v1/models", {"Authorization": f"Bearer {v}"})

    # OpenAI admin ключ (проверяем admin-эндпоинтом)
    if key_name == "creds.openai_admin_key":
        return _req_ok("GET", "https://api.openai.com/v1/organization/admin_api_keys", {"Authorization": f"Bearer {v}"})

    # Gemini: x-goog-api-key header, GET /v1beta/models :contentReference[oaicite:2]{index=2}
    if key_name == "creds.gemini_api_key":
        return _req_ok("GET", "https://generativelanguage.googleapis.com/v1beta/models", {"x-goog-api-key": v})

    # Anthropic: GET /v1/models, headers x-api-key + anthropic-version :contentReference[oaicite:3]{index=3}
    if key_name == "creds.anthropic_api_key":
        return _req_ok(
            "GET",
            "https://api.anthropic.com/v1/models",
            {"x-api-key": v, "anthropic-version": "2023-06-01"},
        )

    # Groq (OpenAI-compatible): GET https://api.groq.com/openai/v1/models :contentReference[oaicite:4]{index=4}
    if key_name == "creds.groq_api_key":
        return _req_ok("GET", "https://api.groq.com/openai/v1/models", {"Authorization": f"Bearer {v}"})

    # DeepSeek (OpenAI-compatible, base_url https://api.deepseek.com/v1) :contentReference[oaicite:5]{index=5}
    if key_name == "creds.deepseek_api_key":
        return _req_ok("GET", "https://api.deepseek.com/v1/models", {"Authorization": f"Bearer {v}"})

    # Mistral: Bearer, GET /v1/models :contentReference[oaicite:6]{index=6}
    if key_name == "creds.mistral_api_key":
        return _req_ok("GET", "https://api.mistral.ai/v1/models", {"Authorization": f"Bearer {v}"})

    # xAI: base https://api.x.ai, Bearer :contentReference[oaicite:7]{index=7}
    if key_name == "creds.xai_api_key":
        return _req_ok("GET", "https://api.x.ai/v1/models", {"Authorization": f"Bearer {v}"})

    # Deepgram: Authorization: Token <API_KEY>, GET /v1/projects :contentReference[oaicite:8]{index=8}
    if key_name == "creds.deepgram_api_key":
        return _req_ok("GET", "https://api.deepgram.com/v1/projects", {"Authorization": f"Token {v}"})

    return False, "UNSUPPORTED_KEY"


@router.post("/{rid}/verify")
async def verify_api_keys_resource(
    rid: str,
    payload: dict = Body(...),
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    rid_uuid = UUID(str(rid))

    row = db.query(Resource).filter(Resource.id == rid_uuid).first()
    if not row or row.user_id != user.id or row.provider != "api_keys":
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    meta_in = payload.get("meta_json") or {}
    creds_in = meta_in.get("creds") or {}

    # === ЕДИНАЯ ИНИЦИАЛИЗАЦИЯ ===
    meta = row.meta_json or {}
    meta.setdefault("creds", {})
    meta.setdefault("verified", {})

    creds_saved: dict[str, str] = meta["creds"]
    verified_map: dict[str, dict] = meta["verified"]

    KEYS = [
        "openai_api_key",
        "openai_admin_key",
        "gemini_api_key",
        "anthropic_api_key",
        "groq_api_key",
        "deepseek_api_key",
        "mistral_api_key",
        "xai_api_key",
        "deepgram_api_key",
    ]

    # === 1. УДАЛЕНИЕ СТЁРТЫХ КЛЮЧЕЙ ===
    for field in KEYS:
        if field in creds_in and not (creds_in.get(field) or "").strip():
            creds_saved.pop(field, None)
            verified_map.pop(f"creds.{field}", None)

    # === 2. ПРОВЕРКА ЗАПОЛНЕННЫХ ===
    failed = []
    now = _utc_iso()

    for field in KEYS:
        val = (creds_in.get(field) or "").strip()
        if not val:
            continue

        key_name = f"creds.{field}"
        ok, err = _verify_key(key_name, val)

        verified_map[key_name] = {
            "ok": bool(ok),
            "error": err,
            "checked_at": now,
        }

        if ok:
            creds_saved[field] = val
        else:
            failed.append(key_name)

    # === 3. СОХРАНЕНИЕ ===
    meta["creds"] = creds_saved
    meta["verified"] = verified_map
    row.meta_json = meta

    db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "ok": True,
        "verified": verified_map,
        "failed": failed,
    }
