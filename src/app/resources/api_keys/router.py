# src/app/resources/api_keys/router.py
from __future__ import annotations

from uuid import UUID

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
        meta_json={"creds": {}, "phase": "new", "error": None},
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
    # validate id
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

    row.label = label
    row.meta_json = meta_json

    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "id": str(row.id)}
