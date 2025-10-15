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
        meta = row.meta_json or {}
        ok, issues = validate_provider_meta(row.provider, meta)

        # если схема не прошла
        if not ok:
            detailed = []
            for it in issues:
                if it.startswith("MISSING:"):
                    detailed.append(f"Отсутствует поле {it.split(':', 1)[1]}")
                elif it.startswith("EMPTY:"):
                    detailed.append(f"Поле пустое {it.split(':', 1)[1]}")
                elif it.startswith("TYPE:"):
                    detailed.append(f"Неверный тип {it.split(':', 1)[1]}")
                else:
                    detailed.append(it)
            return JSONResponse(
                {
                    "ok": False,
                    "error": "META_INVALID",
                    "message": "Ресурс не может быть активирован — неполные данные.",
                    "issues": detailed,
                    "status": row.status,
                    "phase": row.phase,
                },
                status_code=400,
            )

        # доп.проверка для Telegram: есть ли активная сессия
        if row.provider == "telegram":
            creds = meta.get("creds") or {}
            if not creds.get("string_session"):
                return JSONResponse(
                    {
                        "ok": False,
                        "error": "MISSING_SESSION",
                        "message": "Сессия Telegram не активирована. Введите код подтверждения.",
                        "issues": ["creds.string_session"],
                        "status": row.status,
                        "phase": row.phase,
                    },
                    status_code=400,
                )

        # всё ок → активируем
        row.status = "active"
        if row.phase in (None, "paused", "error", "draft"):
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


# ───────────────────────────────────────────────────────────────
# 🔹 Получение ресурса по ID
# ───────────────────────────────────────────────────────────────
@router.get("/{rid}")
async def api_resource_get(rid: str, request: Request, db: SASession = Depends(get_db)):
    """
    Возвращает полный объект ресурса пользователя.
    Используется страницей Telegram и модалками на фронте.
    """
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

    return {
        "ok": True,
        "id": str(row.id),
        "provider": row.provider,
        "label": row.label,
        "status": row.status,
        "phase": row.phase,
        "meta_json": row.meta_json or {},
        "created_at": str(row.created_at) if row.created_at else None,
        "updated_at": str(row.updated_at) if row.updated_at else None,
    }


# ───────────────────────────────────────────────────────────────
# 🔹 Обновление ресурса по ID
# ───────────────────────────────────────────────────────────────
@router.put("/{rid}")
async def api_resource_update(
        rid: str,
        payload: dict = Body(...),
        request: Request = None,
        db: SASession = Depends(get_db),
):
    """
    Обновляет label и meta_json ресурса.
    Используется страницей Telegram для сохранения настроек.
    """
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

    # обновляем поля
    row.label = (payload.get("label") or row.label or "").strip()
    if isinstance(payload.get("meta_json"), dict):
        row.meta_json = merge_meta_json(row.meta_json, payload["meta_json"])
    row.updated_at = datetime.now(timezone.utc)

    db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "ok": True,
        "id": str(row.id),
        "provider": row.provider,
        "label": row.label,
        "status": row.status,
        "phase": row.phase,
        "meta_json": row.meta_json or {},
    }


def merge_meta_json(old_meta, new_meta):
    old_meta = old_meta or {}
    new_meta = new_meta or {}
    merged = old_meta.copy()
    creds = old_meta.get("creds") or {}
    merged.update(new_meta)
    merged["creds"] = creds  # не трогаем чувствительные данные
    return merged
