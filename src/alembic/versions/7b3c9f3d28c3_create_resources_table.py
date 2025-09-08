"""Create unified resources table

Revision ID: 7b3c9f3d28c3
Revises: 20250908_avito_flru
Create Date: 2025-09-10 20:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# --- Alembic identifiers ---
revision = "7b3c9f3d28c3"
down_revision = "20250908_avito_flru"
branch_labels = None
depends_on = None


def upgrade():
    # --- удаляем старые таблицы, если остались ---
    op.execute("DROP TABLE IF EXISTS service_accounts CASCADE;")
    op.execute("DROP TABLE IF EXISTS tg_accounts CASCADE;")
    op.execute("DROP TABLE IF EXISTS service_rules CASCADE;")
    op.execute("DROP TABLE IF EXISTS prompts CASCADE;")

    # расширение для UUID
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    # --- создаём таблицу resources ---
    op.create_table(
        "resources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.Integer,
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),   # telegram | avito | flru | voice | ...
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="new"),   # new|active|paused|error|blocked
        sa.Column("phase", sa.String(length=20), nullable=False, server_default="ready"),  # ready|starting|running|error|paused
        sa.Column("last_error_code", sa.String(length=50)),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column("meta_json", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # --- индексы ---
    op.create_index("ix_resources_user", "resources", ["user_id"])
    op.create_index("ix_resources_provider", "resources", ["provider"])
    op.create_index("ix_resources_status", "resources", ["status"])
    op.create_index("ix_resources_phase", "resources", ["phase"])
    op.create_index("ix_resources_meta_gin", "resources", [sa.text("meta_json")], postgresql_using="gin")


def downgrade():
    op.drop_index("ix_resources_meta_gin", table_name="resources")
    op.drop_index("ix_resources_phase", table_name="resources")
    op.drop_index("ix_resources_status", table_name="resources")
    op.drop_index("ix_resources_provider", table_name="resources")
    op.drop_index("ix_resources_user", table_name="resources")
    op.drop_table("resources")

    # старые таблицы назад не возвращаем
