from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Request, Depends, HTTPException, status, Body
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session as SASession
from src.models import Resource
from src.app.core.db import get_db
from src.app.core.auth import get_current_user
from src.app.providers import PROVIDERS, validate_provider_meta

router = APIRouter(prefix="/api/resources", tags=["resources"])


@router.get("/list")
async def api_resources_list(request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    q = select(Resource).where(Resource.user_id == user.id)
    created_at_col = getattr(Resource, "created_at", None)
    if created_at_col is not None:
        q = q.order_by(created_at_col.desc())
    rows = db.execute(q).scalars().all()

    items = []
    for r in rows:
        meta = r.meta_json or {}
        ok, issues = validate_provider_meta(r.provider, meta)
        items.append({
            "id": str(r.id),
            "provider": r.provider,
            "label": r.label,
            "status": r.status,
            "phase": r.phase,
            "last_error_code": getattr(r, "last_error_code", None),
            "valid": ok,
            "issues": issues,
        })
    return {"ok": True, "items": items}


@router.post("/toggle")
async def api_resources_toggle(payload: dict, request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    rid = (payload.get("id") or "").strip()
    action = (payload.get("action") or "").strip()  # 'activate' | 'pause'
    if not rid or action not in {"activate", "pause"}:
        return JSONResponse({"ok": False, "error": "VALIDATION"}, status_code=400)

    try:
        rid_uuid = UUID(rid)
    except ValueError:
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    row = db.execute(select(Resource).where(Resource.id == rid_uuid)).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    role_val = user.role.value if hasattr(user.role, "value") else str(user.role)
    if role_val != "admin" and row.user_id != user.id:
        raise HTTPException(status_code=403, detail="FORBIDDEN")

    if action == "activate":
        ok, issues = validate_provider_meta(row.provider, row.meta_json or {})
        if not ok:
            return JSONResponse(
                {"ok": False, "error": "META_INVALID", "issues": issues},
                status_code=400,
            )
        row.status = "active"
        if row.phase in (None, "paused", "error"):
            row.phase = "ready"
    else:
        row.status = "paused"
        row.phase = "paused"

    db.add(row)
    db.commit()
    return {"ok": True, "status": row.status, "phase": row.phase}


@router.post("/add")
async def api_resources_add(payload: dict, request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    provider = (payload.get("provider") or "").strip()
    label = (payload.get("label") or "").strip() or provider
    meta = payload.get("meta_json")

    if provider not in PROVIDERS:
        return JSONResponse({"ok": False, "error": "UNKNOWN_PROVIDER"}, status_code=400)

    if not isinstance(meta, dict):
        meta = PROVIDERS[provider]["template"]

    new_res = Resource(
        user_id=user.id,
        provider=provider,
        label=label,
        status="paused",
        phase="draft",
        meta_json=meta,
        created_at=datetime.now(timezone.utc),
    )
    db.add(new_res)
    db.commit()
    db.refresh(new_res)

    return {
        "ok": True,
        "id": str(new_res.id),
        "provider": new_res.provider,
        "label": new_res.label,
        "status": new_res.status,
        "phase": new_res.phase,
    }
