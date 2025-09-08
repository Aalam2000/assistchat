# scripts/check_models.py
from __future__ import annotations
import sys
from collections import defaultdict

from sqlalchemy import MetaData
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import Column
from sqlalchemy.engine import Engine

# наш общий engine / Base и регистрация моделей
from src.common.db import engine, Base  # Base, на котором объявлены модели
import src.models as models  # важно: регистрирует таблицы в Base.metadata

DIALECT = postgresql.dialect()

def col_type_str(col: Column) -> str:
    # приведение типа к строке так же, как его «видит» Postgres
    try:
        return col.type.compile(dialect=DIALECT)
    except Exception:
        return repr(col.type)

def compare(engine: Engine) -> int:
    # таблицы из моделей
    model_md = Base.metadata
    model_tables = {name: tbl for name, tbl in model_md.tables.items()}

    # таблицы из БД (факт)
    db_md = MetaData()
    db_md.reflect(bind=engine)
    db_tables = {name: tbl for name, tbl in db_md.tables.items()}

    errors = 0
    report = []

    # проверяем только те таблицы, для которых есть модели
    for tname, mt in model_tables.items():
        if tname not in db_tables:
            errors += 1
            report.append(f"[TABLE MISSING IN DB] {tname}")
            continue

        dt = db_tables[tname]

        m_cols = {c.name: c for c in mt.columns}
        d_cols = {c.name: c for c in dt.columns}

        # отсутствующие / лишние колонки
        missing = sorted(set(m_cols) - set(d_cols))
        extra   = sorted(set(d_cols) - set(m_cols))

        if missing:
            errors += 1
            report.append(f"[{tname}] missing columns in DB: {', '.join(missing)}")
        if extra:
            report.append(f"[{tname}] extra columns in DB (ok, если осознанно): {', '.join(extra)}")

        # сравнение общих колонок
        common = sorted(set(m_cols) & set(d_cols))
        for cname in common:
            mc, dc = m_cols[cname], d_cols[cname]

            issues = []

            # тип
            m_t, d_t = col_type_str(mc), col_type_str(dc)
            if m_t != d_t:
                issues.append(f"type model={m_t!r} db={d_t!r}")

            # nullable
            if bool(mc.nullable) != bool(dc.nullable):
                issues.append(f"nullable model={mc.nullable} db={dc.nullable}")

            # PK
            if bool(mc.primary_key) != bool(dc.primary_key):
                issues.append(f"primary_key model={mc.primary_key} db={dc.primary_key}")

            if issues:
                errors += 1
                report.append(f"[{tname}.{cname}] " + "; ".join(issues))

        # состав PK целиком
        m_pk = tuple(c.name for c in mt.primary_key.columns)
        d_pk = tuple(c.name for c in dt.primary_key.columns)
        if m_pk != d_pk:
            errors += 1
            report.append(f"[{tname}] PK mismatch model={m_pk} db={d_pk}")

        if not any(line.startswith(f"[{tname}]") or line.startswith(f"[TABLE MISSING IN DB] {tname}") or line.startswith(f"[{tname}.") for line in report):
            report.append(f"[{tname}] OK")

    # таблицы, которых нет в моделях (информативно)
    unmapped = sorted(set(db_tables) - set(model_tables))
    if unmapped:
        report.append(f"[INFO] tables present in DB but not in models: {', '.join(unmapped)}")

    # вывод
    status = "FAIL" if errors else "OK"
    print(f"Model ⇄ DB check: {status}")
    for line in report:
        print(line)

    return 1 if errors else 0

if __name__ == "__main__":
    sys.exit(compare(engine))
