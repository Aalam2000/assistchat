# src/app/resources/common.py
from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Request, Depends, HTTPException, Body
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session as SASession

from src.app.core.auth import get_current_user
from src.app.core.db import get_db
from src.app.providers import PROVIDERS, validate_provider_meta
from src.models import Resource

router = APIRouter(prefix="/api/resources", tags=["resources"])

# ───────────────────────────────────────────────────────────────
# 🔹 Список ресурсов пользователя
# ───────────────────────────────────────────────────────────────
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


# ───────────────────────────────────────────────────────────────
# 🔹 Переключение статуса ресурса
# ───────────────────────────────────────────────────────────────
@router.post("/toggle")
async def api_resources_toggle(payload: dict, request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    rid = (payload.get("id") or "").strip()
    action = (payload.get("action") or "").strip()
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
        meta = row.meta_json or {}
        ok, issues = validate_provider_meta(row.provider, meta)
        if not ok:
            return JSONResponse(
                {"ok": False, "error": "META_INVALID", "issues": issues},
                status_code=400,
            )
        if row.provider == "telegram":
            creds = meta.get("creds") or {}
            if not creds.get("string_session"):
                return JSONResponse(
                    {"ok": False, "error": "MISSING_SESSION"},
                    status_code=400,
                )
        row.status = "active"
        if row.phase in (None, "paused", "error", "draft"):
            row.phase = "ready"
    else:
        row.status = "paused"
        row.phase = "paused"

    db.add(row)
    db.commit()
    # 🔹 после изменения статуса вызываем проверку бота
    try:
        from src.app.modules.bot.manager import BotManager
        mgr = BotManager()
        mgr.preflight(user_id=user.id)  # выполняет пересинхронизацию активных ресурсов
    except Exception as e:
        print(f"[TG_RES_TOGGLE] preflight error: {e}")

    return {"ok": True, "status": row.status, "phase": row.phase}


# ───────────────────────────────────────────────────────────────
# 🔹 Добавление нового ресурса
# ───────────────────────────────────────────────────────────────
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
    return {"ok": True, "id": str(new_res.id), "provider": new_res.provider,
            "label": new_res.label, "status": new_res.status, "phase": new_res.phase}

# ───────────────────────────────────────────────────────────────
# 🔹 Провайдеры (новые добавленные ручки)
# ───────────────────────────────────────────────────────────────
@router.get("/providers")
def api_providers():
    items = []
    for key, cfg in PROVIDERS.items():
        items.append({
            "key": key,
            "name": cfg.get("title", key),
            "template": cfg.get("template", {}),
            "help": cfg.get("help", {}),
        })
    return {"ok": True, "providers": items}


@router.get("/providers/{key}/schema")
def api_provider_schema(key: str):
    cfg = PROVIDERS.get(key)
    if not cfg:
        raise HTTPException(status_code=404, detail="UNKNOWN_PROVIDER")
    return {"ok": True, "schema": cfg.get("schema", {}),
            "template": cfg.get("template", {}), "help": cfg.get("help", {})}



# ───────────────────────────────────────────────────────────────
# 🔹 Получение ресурса по ID
# ───────────────────────────────────────────────────────────────
@router.get("/{rid}")
async def api_resource_get(rid: str, request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    try:
        rid_uuid = UUID(rid)
    except ValueError:
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    row = db.get(Resource, rid_uuid)
    if not row:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    if row.user_id != user.id and getattr(user.role, "value", str(user.role)) != "admin":
        raise HTTPException(status_code=403, detail="FORBIDDEN")

    return {"ok": True, "id": str(row.id), "provider": row.provider,
            "label": row.label, "status": row.status, "phase": row.phase,
            "meta_json": row.meta_json or {}}


# ───────────────────────────────────────────────────────────────
# 🔹 Обновление ресурса
# ───────────────────────────────────────────────────────────────
@router.put("/{rid}")
async def api_resource_update(rid: str, payload: dict = Body(...),
                              request: Request = None, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    try:
        rid_uuid = UUID(rid)
    except ValueError:
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    row = db.get(Resource, rid_uuid)
    if not row:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    if row.user_id != user.id and getattr(user.role, "value", str(user.role)) != "admin":
        raise HTTPException(status_code=403, detail="FORBIDDEN")

    row.label = (payload.get("label") or row.label or "").strip()
    if isinstance(payload.get("meta_json"), dict):
        row.meta_json = merge_meta_json(row.meta_json, payload["meta_json"])
    row.updated_at = datetime.now(timezone.utc)

    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "id": str(row.id), "provider": row.provider,
            "label": row.label, "status": row.status, "phase": row.phase,
            "meta_json": row.meta_json or {}}


# ───────────────────────────────────────────────────────────────
# Вспомогательная функция
# ───────────────────────────────────────────────────────────────
def merge_meta_json(old_meta, new_meta):
    old_meta = old_meta or {}
    new_meta = new_meta or {}
    merged = old_meta.copy()

    old_creds = old_meta.get("creds") or {}
    new_creds = (new_meta.get("creds") or {}).copy()
    merged_creds = {**old_creds, **new_creds}

    merged.update(new_meta)
    merged["creds"] = merged_creds
    return merged


# ───────────────────────────────────────────────────────────────
# 🔹 Удаление ресурса
# ───────────────────────────────────────────────────────────────
@router.delete("/{rid}")
async def api_resource_delete(rid: str, request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    from uuid import UUID
    try:
        rid_uuid = UUID(rid)
    except ValueError:
        return JSONResponse({"ok": False, "error": "INVALID_ID"}, status_code=400)

    row = db.get(Resource, rid_uuid)
    if not row:
        return JSONResponse({"ok": False, "error": "NOT_FOUND"}, status_code=404)

    role_val = getattr(user.role, "value", str(user.role))
    if role_val != "admin" and row.user_id != user.id:
        return JSONResponse({"ok": False, "error": "FORBIDDEN"}, status_code=403)

    db.delete(row)
    db.commit()
    return {"ok": True, "deleted": str(rid)}
