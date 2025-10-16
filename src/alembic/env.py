# src/alembic/env.py
from __future__ import annotations
import os
from dotenv import load_dotenv
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# Alembic config
config = context.config

# Подхватываем .env из корня проекта (docker-compose его монтирует)
load_dotenv()

# Логи Alembic
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Метаданные моделей
target_metadata = None

# DATABASE_URL из ENV (docker-compose его передаёт)
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
else:
    DB_USER = os.getenv("DB_USER", "")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "")
    DB_HOST = os.getenv("DB_HOST", "db")
    DB_PORT = os.getenv("DB_PORT", "5432")
    url = f"postgresql+psycopg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    config.set_main_option("sqlalchemy.url", url)

# ── ФИЛЬТР ОБЪЕКТОВ: белый список (-x tables=a,b) и исключения (-x ignore_tables=x,y)
_x = context.get_x_argument(as_dictionary=True)
_only = set(filter(None, (_x.get("tables") or "").split(",")))
_ignore = set(filter(None, (_x.get("ignore_tables") or "").split(",")))

def _include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table":
        if _only and name not in _only:
            return False
        if name in _ignore:
            return False
    elif type_ == "column":
        t = getattr(obj.table, "name", None)
        if _only and t not in _only:
            return False
        if t in _ignore:
            return False
    return True

def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_object=_include_object,
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
