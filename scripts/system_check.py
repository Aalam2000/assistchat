# scripts/system_check.py
"""
system_check.py — единый скрипт проверки состояния проекта.

Что делает:
1. Проверяет FastAPI — доступность /openapi.json.
2. Проверяет подключение к БД — выполняет SELECT 1.
3. Сравнивает модели и БД:
   - наличие таблиц,
   - колонки (типы, nullable, PK),
   - лишние/отсутствующие таблицы.
4. Формирует отчёт:
   - [OK]   — всё в порядке
   - [FAIL] — ошибка, требует исправления
   - [WARN] — предупреждение (например, лишние колонки)
   - [INFO] — дополнительная информация
   - [HINT] — подсказка, как устранить проблему
   - [SKIP] — шаг пропущен (например, БД недоступна)
5. Выводит сводку: количество OK/FAIL/WARN/INFO/HINT/SKIP.
6. Код возврата:
   - 0 — ошибок нет
   - 1 — есть [FAIL]

Как запускать:
- На хосте (для быстрой проверки FastAPI):
    python scripts/system_check.py
  При недоступности БД выдаст подсказку.

- В контейнере (полная проверка):
    docker compose run --rm web     python scripts/system_check.py
    docker compose run --rm migrate python scripts/system_check.py

Назначение:
Универсальный health-check: сразу видно, что работает, где ошибки и что нужно исправить.
"""


from __future__ import annotations

import os
import re
import sys
import pathlib
from collections import Counter

from dotenv import load_dotenv
from sqlalchemy import MetaData, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import Column
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from fastapi.testclient import TestClient

# --- Корень проекта и sys.path ---
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# --- .env ---
dotenv_path = ROOT / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)

# --- Импорты приложения (регистрация моделей) ---
# Важно: engine не коннектится до первого запроса — безопасно импортировать.
from src.common.db import engine, Base
import src.models as _models  # noqa: F401  (нужно для регистрации таблиц в Base.metadata)

DIALECT = postgresql.dialect()


def _is_docker() -> bool:
    # признак исполнения внутри контейнера
    return os.path.exists("/.dockerenv") or os.environ.get("RUNNING_IN_DOCKER") == "1"


def _mk_hint_for_docker(reason: str) -> list[str]:
    return [
        f"[HINT] {reason}",
        "[HINT] Запусти внутри контейнера, чтобы был доступ к сети docker:",
        "[HINT]   docker compose run --rm web     python scripts/system_check.py",
        "[HINT] или docker compose run --rm migrate python scripts/system_check.py",
    ]


def col_type_str(col: Column) -> str:
    try:
        return col.type.compile(dialect=DIALECT)
    except Exception:
        return repr(col.type)


def check_fastapi() -> list[str]:
    report: list[str] = []
    try:
        # Ленивая загрузка app — чтобы любые ошибки импорта попали в отчёт, а не падали трассой.
        from src.app.main import app  # noqa
        client = TestClient(app)
        r = client.get("/openapi.json")
        if r.status_code == 200:
            report.append("[OK] FastAPI: /openapi.json доступен")
        else:
            report.append(f"[FAIL] FastAPI: статус {r.status_code} на /openapi.json")
    except Exception as e:
        report.append(f"[FAIL] FastAPI init: {e!r}")
    return report


def check_db_connect() -> list[str]:
    report: list[str] = []
    try:
        with engine.begin() as conn:
            conn.execute(text("select 1"))
        report.append("[OK] DB: соединение работает")
    except Exception as e:
        msg = f"[FAIL] DB connect: {e!r}"
        report.append(msg)

        # Узнаваемые симптомы: запуск с хоста и host='db' из docker-сети
        e_text = repr(e)
        if ("getaddrinfo failed" in e_text) or ("Name or service not known" in e_text):
            # Подсказка только если мы не в контейнере
            if not _is_docker():
                report.extend(_mk_hint_for_docker("Похоже, имя хоста БД из docker-сети недоступно с хоста."))
    return report


def check_models_vs_db(engine: Engine) -> list[str]:
    """
    Глубокая сверка моделей и БД.
    Никогда не бросает исключения — только заполняет report.
    """
    report: list[str] = []
    try:
        model_md = Base.metadata
        model_tables = {name: tbl for name, tbl in model_md.tables.items()}

        db_md = MetaData()
        # Может бросить OperationalError, если нет коннекта/резолва — оборачиваем.
        db_md.reflect(bind=engine)
        db_tables = {name: tbl for name, tbl in db_md.tables.items()}

        errors = 0

        for tname, mt in model_tables.items():
            if tname not in db_tables:
                errors += 1
                report.append(f"[FAIL] [TABLE MISSING IN DB] {tname}")
                continue

            dt = db_tables[tname]
            m_cols = {c.name: c for c in mt.columns}
            d_cols = {c.name: c for c in dt.columns}

            missing = sorted(set(m_cols) - set(d_cols))
            extra = sorted(set(d_cols) - set(m_cols))

            if missing:
                errors += 1
                report.append(f"[FAIL] [{tname}] missing columns in DB: {', '.join(missing)}")
            if extra:
                report.append(f"[WARN] [{tname}] extra columns in DB (ok, если осознанно): {', '.join(extra)}")

            common = sorted(set(m_cols) & set(d_cols))
            for cname in common:
                mc, dc = m_cols[cname], d_cols[cname]
                issues = []

                m_t, d_t = col_type_str(mc), col_type_str(dc)
                if m_t != d_t:
                    issues.append(f"type model={m_t!r} db={d_t!r}")
                if bool(mc.nullable) != bool(dc.nullable):
                    issues.append(f"nullable model={mc.nullable} db={dc.nullable}")
                if bool(mc.primary_key) != bool(dc.primary_key):
                    issues.append(f"primary_key model={mc.primary_key} db={dc.primary_key}")

                if issues:
                    errors += 1
                    report.append(f"[FAIL] [{tname}.{cname}] " + "; ".join(issues))

            m_pk = tuple(c.name for c in mt.primary_key.columns)
            d_pk = tuple(c.name for c in dt.primary_key.columns)
            if m_pk != d_pk:
                errors += 1
                report.append(f"[FAIL] [{tname}] PK mismatch model={m_pk} db={d_pk}")

            # Если по таблице ни FAIL/WARN не добавилось — значит ОК
            if not any(
                line.startswith(f"[FAIL] [{tname}")
                or line.startswith(f"[WARN] [{tname}")
                for line in report
            ):
                report.append(f"[OK] [{tname}] таблица совпадает")

        unmapped = sorted(set(db_tables) - set(model_tables))
        if unmapped:
            report.append(f"[INFO] В БД есть таблицы без моделей: {', '.join(unmapped)}")

        report.insert(0, "Model ⇄ DB check: FAIL" if any(l.startswith("[FAIL]") for l in report) else "Model ⇄ DB check: OK")

    except SQLAlchemyError as e:
        # Ошибка подключения/рефлекта — оформляем как FAIL + HINT
        msg = f"[FAIL] Models vs DB: не удалось прочитать схему БД: {e!r}"
        report.append(msg)

        e_text = repr(e)
        if ("getaddrinfo failed" in e_text) or ("Name or service not known" in e_text):
            if not _is_docker():
                report.extend(_mk_hint_for_docker("Рефлект схемы невозможен с хоста: имя БД из docker-сети недоступно."))
        elif "Connection refused" in e_text:
            report.append("[HINT] Проверь, что контейнер БД запущен и здоров (healthcheck=healthy).")
        else:
            # Генерик-подсказка, чтобы не оставлять пользователя без направления
            report.append("[HINT] Проверь DATABASE_URL и сетевую доступность БД из текущего окружения.")

    except Exception as e:
        report.append(f"[FAIL] Models vs DB: непредвиденная ошибка: {e!r}")

    return report


def summarize(lines: list[str]) -> str:
    counts = Counter()
    for line in lines:
        tag = line.split("]", 1)[0] + "]" if line.startswith("[") else ""
        if tag:
            counts[tag] += 1

    # Нормализуем имена ключей для печати
    def c(label: str) -> int:
        for k in counts:
            if k.startswith(f"[{label}]"):
                return counts[k]
        return 0

    return (
        "\n--- SUMMARY ---\n"
        f"OK: {c('OK')} | FAIL: {c('FAIL')} | WARN: {c('WARN')} | INFO: {c('INFO')} | HINT: {c('HINT')} | SKIP: {c('SKIP')}"
    )


def main() -> int:
    report: list[str] = []

    # 1) FastAPI
    report.extend(check_fastapi())

    # 2) DB connect
    db_report = check_db_connect()
    report.extend(db_report)
    db_ok = not any(line.startswith("[FAIL]") for line in db_report)

    # 3) Models vs DB (выполняем только если коннект есть)
    if db_ok:
        report.extend(check_models_vs_db(engine))
    else:
        report.append("[SKIP] Models vs DB: пропущено из-за ошибки соединения с БД")

    # Вывод
    for line in report:
        print(line)

    print(summarize(report))

    # Код выхода: есть хоть один FAIL — 1, иначе 0
    return 1 if any(l.startswith("[FAIL]") for l in report) else 0


if __name__ == "__main__":
    sys.exit(main())
