# scripts/smoke_check.py
from __future__ import annotations

import sys
import pathlib
import os
from dotenv import load_dotenv
from sqlalchemy import text, inspect
from fastapi.testclient import TestClient

# --- Корень проекта и sys.path ---
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# --- Загружаем .env ---
dotenv_path = ROOT / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)

# --- Импорты приложения ---
from src.app.main import app
from src.common.db import engine, Base


def main() -> int:
    ok = True

    # 1) FastAPI поднимается
    try:
        client = TestClient(app)
        r = client.get("/openapi.json")
        if r.status_code == 200:
            print("[OK] FastAPI: /openapi.json доступен")
        else:
            print(f"[FAIL] FastAPI: статус {r.status_code}")
            ok = False
    except Exception as e:
        print("[FAIL] FastAPI init:", repr(e))
        ok = False

    # 2) Подключение к БД
    try:
        with engine.begin() as conn:
            conn.execute(text("select 1"))
        print("[OK] DB: соединение работает")
    except Exception as e:
        print("[FAIL] DB connect:", repr(e))
        ok = False

    # 3) Таблицы в БД vs модели
    try:
        insp = inspect(engine)
        db_tables = set(insp.get_table_names())
        model_tables = set(Base.metadata.tables.keys())

        extra_db = db_tables - model_tables     # есть в БД, нет в моделях
        missing_db = model_tables - db_tables   # есть в моделях, нет в БД

        if not extra_db and not missing_db:
            print("[OK] Models: все таблицы в БД и коде совпадают")
        else:
            if extra_db:
                print("[WARN] В БД есть лишние таблицы:", ", ".join(sorted(extra_db)))
            if missing_db:
                print("[FAIL] В коде есть модели без таблиц в БД:", ", ".join(sorted(missing_db)))
                ok = False
    except Exception as e:
        print("[FAIL] Inspect DB tables:", repr(e))
        ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
