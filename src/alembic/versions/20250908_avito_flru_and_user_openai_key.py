"""Add Avito/FL.ru tables, extend messages, add users.openai_api_key

Revision ID: 20250908_avito_flru
Revises: c4af6c51f292
Create Date: 2025-09-08

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

# Идентификаторы ревизий
revision = "20250908_avito_flru"
down_revision = "c4af6c51f292"
branch_labels = None
depends_on = None


def upgrade():
    # 1) users.openai_api_key
    op.add_column(
        "users",
        sa.Column("openai_api_key", sa.Text(), nullable=True)
    )

    # 2) prompts (библиотека промптов)
    op.create_table(
        "prompts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("params", pg.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_prompts_user_id", "prompts", ["user_id"], unique=False)

    # 3) service_accounts (подключения к провайдерам: avito, flru)
    op.create_table(
        "service_accounts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),                        # 'avito' | 'flru' | ...
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'paused'")),
        sa.Column("external_id", sa.Text(), nullable=True),                      # id/username на площадке
        sa.Column("settings", pg.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("credentials_enc", sa.LargeBinary(), nullable=True),           # шифрованные cookie/token
        sa.Column("prompt_id", sa.String(length=36), sa.ForeignKey("prompts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_service_accounts_user_provider", "service_accounts", ["user_id", "provider"], unique=False)
    op.create_index("ix_service_accounts_status", "service_accounts", ["status"], unique=False)

    # 4) service_rules (бел/чёрные списки на подключение)
    op.create_table(
        "service_rules",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("service_id", sa.String(length=36), sa.ForeignKey("service_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),          # 'whitelist' | 'blacklist'
        sa.Column("target_type", sa.Text(), nullable=False),   # 'user'|'category'|'keyword'|'region'|'regex'|...
        sa.Column("target_value", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_service_rules_service_kind", "service_rules", ["service_id", "kind"], unique=False)

    # 5) leads (заявки/диалоги с площадок)
    op.create_table(
        "leads",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("service_id", sa.String(length=36), sa.ForeignKey("service_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("budget", sa.Numeric(12, 2), nullable=True),
        sa.Column("customer_ref", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'found'")),   # found|messaged|replied|negotiating|won|lost
        sa.Column("meta", pg.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_leads_service_status", "leads", ["service_id", "status"], unique=False)
    op.create_unique_constraint("uq_leads_provider_external", "leads", ["provider", "external_id"])

    # 6) messages — расширяем под внешние площадки
    op.add_column("messages", sa.Column("service_id", sa.String(length=36), nullable=True))
    op.add_column("messages", sa.Column("provider", sa.Text(), nullable=True))
    op.add_column("messages", sa.Column("external_chat_id", sa.Text(), nullable=True))
    op.add_column("messages", sa.Column("external_msg_id", sa.Text(), nullable=True))
    op.create_foreign_key("fk_messages_service", "messages", "service_accounts", ["service_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_messages_service_created", "messages", ["service_id", "created_at"], unique=False)
    op.create_unique_constraint("uq_messages_provider_chat_msg", "messages", ["provider", "external_chat_id", "external_msg_id"])


def downgrade():
    # messages
    op.drop_constraint("uq_messages_provider_chat_msg", "messages", type_="unique")
    op.drop_index("ix_messages_service_created", table_name="messages")
    op.drop_constraint("fk_messages_service", "messages", type_="foreignkey")
    op.drop_column("messages", "external_msg_id")
    op.drop_column("messages", "external_chat_id")
    op.drop_column("messages", "provider")
    op.drop_column("messages", "service_id")

    # leads
    op.drop_constraint("uq_leads_provider_external", "leads", type_="unique")
    op.drop_index("ix_leads_service_status", table_name="leads")
    op.drop_table("leads")

    # rules
    op.drop_index("ix_service_rules_service_kind", table_name="service_rules")
    op.drop_table("service_rules")

    # service_accounts
    op.drop_index("ix_service_accounts_status", table_name="service_accounts")
    op.drop_index("ix_service_accounts_user_provider", table_name="service_accounts")
    op.drop_table("service_accounts")

    # prompts
    op.drop_index("ix_prompts_user_id", table_name="prompts")
    op.drop_table("prompts")

    # users
    op.drop_column("users", "openai_api_key")
