"""add messages and updates_seen

Revision ID: 38ab48e15002
Revises: 165ab7be38b4
Create Date: 2025-08-17 12:14:15.995478

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '38ab48e15002'
down_revision = '165ab7be38b4'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # messages — журнал входящих/исходящих сообщений
    op.create_table(
        "messages",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("account_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("peer_id", sa.BigInteger(), nullable=False),           # tg peer (user/chat/channel)
        sa.Column("peer_type", sa.Text(), nullable=False),               # 'user' | 'chat' | 'channel' | ...
        sa.Column("chat_id", sa.BigInteger(), nullable=True),            # tg chat_id (если есть)
        sa.Column("msg_id", sa.BigInteger(), nullable=True),             # исходный telegram message id
        sa.Column("direction", sa.Text(), nullable=False),               # 'in' | 'out'
        sa.Column("msg_type", sa.Text(), nullable=False, server_default="text"),  # 'text' | 'voice' | ...
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["account_id"], ["tg_accounts.id"], ondelete="CASCADE", name="fk_messages_account"),
    )
    op.create_index("ix_messages_account_peer_created", "messages", ["account_id", "peer_id", "created_at"])

    # updates_seen — антидубли апдейтов/сообщений
    op.create_table(
        "updates_seen",
        sa.Column("account_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("account_id", "chat_id", "message_id", name="pk_updates_seen"),
        sa.ForeignKeyConstraint(["account_id"], ["tg_accounts.id"], ondelete="CASCADE", name="fk_updates_seen_account"),
    )


def downgrade() -> None:
    op.drop_table("updates_seen")
    op.drop_index("ix_messages_account_peer_created", table_name="messages")
    op.drop_table("messages")