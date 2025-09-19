"""replace account_id with resource_id in messages"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# ревизии
revision = "0c7d905c79ff"
down_revision = "2a2a919a38d6"  # твоя предыдущая миграция
branch_labels = None
depends_on = None


def upgrade():
    # Удаляем старые записи, чтобы не мешали
    op.execute("DELETE FROM messages")

    # Удаляем старый account_id
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.drop_column("account_id")

    # Добавляем новый resource_id (NOT NULL)
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.add_column(sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False))
        batch_op.create_foreign_key(
            "fk_messages_resource",
            "resources",
            ["resource_id"],
            ["id"],
            ondelete="CASCADE"
        )


def downgrade():
    # Откатываем обратно
    with op.batch_alter_table("messages", schema=None) as batch_op:
        batch_op.drop_constraint("fk_messages_resource", type_="foreignkey")
        batch_op.drop_column("resource_id")
        batch_op.add_column(sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False))
