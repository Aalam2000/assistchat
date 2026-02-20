# src/app/resources/prompt/router.py
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Body
from sqlalchemy.orm import Session as SASession

from src.app.core.auth import get_current_user
from src.app.core.db import get_db
from src.models.resource import Resource

router = APIRouter(prefix="/api/prompt", tags=["prompt"])


@router.post("/create")
async def create_prompt_resource(
    label: str = Form(...),
    db: SASession = Depends(get_db),
    user=Depends(get_current_user),
):
    r = Resource(
        provider="prompt",
        user_id=user.id,
        label=(label or "").strip() or "Prompt",
        status="new",
        meta_json={
            "prompt": {
                "description": "",
                "system_prompt": "",
                "style_rules": "",
                "google_source": "",
                "examples": [],
            }
        },
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"ok": True, "id": str(r.id)}


@router.put("/{rid}")
async def save_prompt_resource(
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
    if row.provider != "prompt":
        raise HTTPException(status_code=400, detail="BAD_PROVIDER")

    label = (payload.get("label") or "").strip() or row.label or "Prompt"
    meta_json = payload.get("meta_json")
    if meta_json is None or not isinstance(meta_json, dict):
        meta_json = row.meta_json or {}

    row.label = label
    row.meta_json = meta_json

    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "id": str(row.id)}
