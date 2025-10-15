# src/app/providers.py
import os
import yaml
from typing import Any, Dict, List, Tuple, Optional

# ── базовый путь к ресурсам ──────────────────────────────────────────────
BASE_PATH = os.path.join(os.path.dirname(__file__), "resources")

# глобальный словарь всех провайдеров
PROVIDERS: Dict[str, Dict[str, Any]] = {}


# ── служебные функции ─────────────────────────────────────────────────────
def _load_yaml(path: str) -> Dict[str, Any]:
    """Безопасно читает YAML-файл и возвращает dict."""
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
    """Разворачивает groups/fields в плоский словарь ключей."""
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
    """Получает значение по пути a.b.c из словаря."""
    cur = meta or {}
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


# ── загрузка всех провайдеров ─────────────────────────────────────────────
def load_all_providers() -> Dict[str, Dict[str, Any]]:
    """Ищет все settings.yaml в подпапках resources/*."""
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


# ── API для остального кода ──────────────────────────────────────────────
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


def validate_provider_meta(provider: str, meta: Dict[str, Any] | None) -> Tuple[bool, List[str]]:
    """Проверка meta_json по схеме из settings.yaml провайдера."""
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


# загружаем при импорте
load_all_providers()
