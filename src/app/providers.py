"""
src/app/providers.py — динамическая загрузка всех провайдеров AssistChat.
Используется botworker и guard bot_enabled для импорта router и worker классов.
"""

import os
import yaml
import importlib
from typing import Any, Dict, List, Tuple, Optional
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException
from src.app.core.db import get_db

from src.models.resource import Resource
from src.app.core.auth import get_current_user

# ── базовый путь к ресурсам ──────────────────────────────────────────────
BASE_PATH = os.path.join(os.path.dirname(__file__), "resources")

# глобальные словари
PROVIDERS: Dict[str, Dict[str, Any]] = {}
WORKER_CACHE: Dict[str, Any] = {}   # provider_name → класс воркера


# ── служебные функции ─────────────────────────────────────────────────────
def _load_yaml(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"[PROVIDERS] Ошибка чтения {path}: {e}")
        return {}


def _normalize_type(t: Optional[str]) -> str:
    if not t:
        return "string"
    t = t.lower()
    if t in {"str"}:
        return "string"
    if t in {"int"}:
        return "number"
    if t in {"string", "password", "number", "textarea", "json", "list", "map", "boolean"}:
        return t
    return "string"


def _flatten_schema(schema_obj: Any) -> Dict[str, Dict[str, Any]]:
    flat: Dict[str, Dict[str, Any]] = {}
    if isinstance(schema_obj, dict) and "groups" not in schema_obj:
        for path, t in schema_obj.items():
            flat[path] = {"type": _normalize_type(t), "required": True}
        return flat

    if isinstance(schema_obj, dict) and isinstance(schema_obj.get("groups"), list):
        for grp in schema_obj["groups"]:
            for f in grp.get("fields") or []:
                key = f.get("key")
                if not key:
                    continue
                flat[key] = {
                    "type": _normalize_type(f.get("type")),
                    "required": bool(f.get("required", True))
                }
    return flat


def _get(meta: Dict[str, Any] | None, path: str) -> Any:
    cur = meta or {}
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


# ── загрузка всех провайдеров ─────────────────────────────────────────────
def load_all_providers() -> Dict[str, Dict[str, Any]]:
    global PROVIDERS
    PROVIDERS.clear()

    if not os.path.isdir(BASE_PATH):
        print(f"[PROVIDERS] Папка {BASE_PATH} не найдена")
        return PROVIDERS

    for folder in os.listdir(BASE_PATH):
        folder_path = os.path.join(BASE_PATH, folder)
        if not os.path.isdir(folder_path):
            continue
        settings_path = os.path.join(folder_path, "settings.yaml")
        if not os.path.exists(settings_path):
            continue

        data = _load_yaml(settings_path)
        if isinstance(data, dict) and data:
            PROVIDERS[folder] = data
            print(f"[PROVIDERS] Загружен провайдер: {folder}")
        else:
            print(f"[PROVIDERS] Пропущен {folder} (пустой settings.yaml)")

    print(f"[PROVIDERS] Всего загружено: {len(PROVIDERS)} провайдер(ов)")
    return PROVIDERS


# ── динамический импорт воркеров ─────────────────────────────────────────
def import_worker(provider: str):
    if provider in WORKER_CACHE:
        return WORKER_CACHE[provider]

    try:
        module = importlib.import_module(f"src.app.resources.{provider}.{provider}")
        worker_cls = getattr(module, f"{provider.capitalize()}Worker", None) or getattr(module, "Worker", None)
        if worker_cls:
            WORKER_CACHE[provider] = worker_cls
            print(f"[PROVIDERS] Импортирован воркер: {provider}")
            return worker_cls
        print(f"[PROVIDERS] Модуль {provider} без класса воркера")
    except ModuleNotFoundError:
        print(f"[PROVIDERS] Провайдер {provider}: модуль не найден (пропущен)")
    except Exception as e:
        print(f"[PROVIDERS] Ошибка импорта воркера {provider}: {e}")

    WORKER_CACHE[provider] = None
    return None


# ── получение активных ресурсов из БД ─────────────────────────────────────
def get_active_resources(db: Session) -> Dict[str, list]:
    from src.models.resource import Resource
    result: Dict[str, list] = {}
    try:
        rows = db.query(Resource).filter(Resource.status == "active").all()
        for r in rows:
            result.setdefault(r.provider, []).append(r)
    except Exception as e:
        print(f"[PROVIDERS] Ошибка при получении активных ресурсов: {e}")
    return result


# ── UI схема для фронтенда ────────────────────────────────────────────────
def get_provider_ui_schema(provider: str) -> Dict[str, Any]:
    cfg = PROVIDERS.get(provider) or {}
    sch = cfg.get("schema")
    if isinstance(sch, dict) and "groups" in sch:
        return sch
    flat = _flatten_schema(sch)
    fields = []
    for path, spec in flat.items():
        fields.append({
            "key": path,
            "label": path,
            "type": spec.get("type", "string"),
            "required": bool(spec.get("required", True)),
        })
    return {"version": 1, "groups": [{"title": "Параметры", "fields": fields}]}


# ── валидация meta_json ───────────────────────────────────────────────────
def validate_provider_meta(provider: str, meta: Dict[str, Any] | None) -> Tuple[bool, List[str]]:
    cfg = PROVIDERS.get(provider)
    if not cfg:
        return False, ["UNKNOWN_PROVIDER"]

    flat = _flatten_schema(cfg.get("schema"))
    problems: List[str] = []

    for path, spec in flat.items():
        t = spec.get("type", "string")
        required = bool(spec.get("required", True))
        val = _get(meta, path)

        if val is None:
            if required:
                problems.append(f"MISSING:{path}")
            continue

        if t in {"string", "password", "textarea"}:
            if not isinstance(val, str):
                problems.append(f"TYPE:{path}")
            elif required and not val.strip():
                problems.append(f"EMPTY:{path}")
        elif t == "number":
            if not isinstance(val, (int, float)):
                problems.append(f"TYPE:{path}")
        elif t == "list":
            if not isinstance(val, list):
                problems.append(f"TYPE:{path}")
        elif t in {"json", "map"}:
            if not isinstance(val, dict):
                problems.append(f"TYPE:{path}")
            elif required and not val:
                problems.append(f"EMPTY:{path}")
        elif t == "boolean":
            if not isinstance(val, bool):
                problems.append(f"TYPE:{path}")
        else:
            problems.append(f"SCHEMA:{path}")

    return (len(problems) == 0), problems


# ── API router для фронтенда /api/providers/* ─────────────────────────────
router = APIRouter(prefix="/api/providers", tags=["Providers"])

@router.get("/list")
async def list_providers():
    """Отдаёт список провайдеров, загруженных из settings.yaml"""
    load_all_providers()
    providers_info = []
    for key, cfg in PROVIDERS.items():
        providers_info.append({
            "key": key,
            "name": cfg.get("name", key.title()),
            "status": "available",
            "description": cfg.get("description", ""),
        })
    return {"ok": True, "providers": providers_info}

@router.get("/{provider}/schema")
async def provider_schema(provider: str):
    """Возвращает JSON-схему для UI конкретного провайдера"""
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Provider '{provider}' not found")
    return {"ok": True, "schema": get_provider_ui_schema(provider)}


# ── автозагрузка при импорте ──────────────────────────────────────────────
load_all_providers()

# ─────────────────────────────────────────────────────────────
# 📋 1. Список ресурсов пользователя  (для index.js)
# ─────────────────────────────────────────────────────────────
@router.get("/resources/list")
async def user_resources_list(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Возвращает список ресурсов, принадлежащих текущему пользователю."""
    try:
        rows = db.query(Resource).filter(Resource.user_id == user.id).all()
        items = [{
            "id": str(r.id),
            "provider": r.provider,
            "label": r.label,
            "status": r.status,
            "phase": r.phase,
            "last_error_code": r.last_error_code,
            "meta": r.meta_json or {"creds": {}}
        } for r in rows]
        return {"ok": True, "items": items}
    except Exception as e:
        print(f"[PROVIDERS] user_resources_list error: {e}")
        return {"ok": False, "items": []}

# ─────────────────────────────────────────────────────────────
# 🗑️  UNIVERSAL DELETE RESOURCE
# ─────────────────────────────────────────────────────────────
@router.delete("/resource/{rid}")
async def delete_resource(
    rid: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Универсальное удаление ресурса (любой провайдер)."""

    try:
        row = db.query(Resource).filter(Resource.id == rid).first()
    except Exception:
        raise HTTPException(status_code=400, detail="BAD_ID")

    if not row:
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    if row.user_id != user.id:
        raise HTTPException(status_code=403, detail="FORBIDDEN")

    # Удаляем строку ресурса
    db.delete(row)
    db.commit()

    return {"ok": True, "deleted": rid}
