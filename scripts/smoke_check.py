from __future__ import annotations
import sys
from sqlalchemy import text
from fastapi.testclient import TestClient

from src.app.main import app
from src.common.db import engine, Base
import src.models as models

def main() -> int:
    ok = True

    # 1) FastAPI поднимается и роуты есть
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

    # 3) Модели зарегистрированы
    expected = {
        "users","tg_accounts","messages","prompts",
        "service_accounts","service_rules","leads",
        "updates_seen","alembic_version",
    }
    have = set(Base.metadata.tables.keys())
    missing = expected - have
    if not missing:
        print("[OK] Models: все ожидаемые таблицы смэпплены")
    else:
        print("[FAIL] Models: нет в метаданных ->", ", ".join(sorted(missing)))
        ok = False

    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
