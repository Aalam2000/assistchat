"""fix resources.user_id to Integer

Revision ID: 2a2a919a38d6
Revises: 7b3c9f3d28c3
Create Date: 2025-09-12 17:52:38.134731

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '2a2a919a38d6'
down_revision = '7b3c9f3d28c3'
branch_labels = None
depends_on = None

def upgrade():
    # удаляем старый FK
    op.drop_constraint("resources_user_id_fkey", "resources", type_="foreignkey")

    # меняем тип user_id → Integer
    op.alter_column(
        "resources",
        "user_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        type_=sa.Integer(),
        existing_nullable=False,
        postgresql_using="user_id::text::integer",
    )

    # создаём новый FK
    op.create_foreign_key(
        "resources_user_id_fkey",
        "resources",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade():
    # удаляем новый FK
    op.drop_constraint("resources_user_id_fkey", "resources", type_="foreignkey")

    # возвращаем тип UUID
    op.alter_column(
        "resources",
        "user_id",
        existing_type=sa.Integer(),
        type_=sa.dialects.postgresql.UUID(as_uuid=True),
        existing_nullable=False,
        postgresql_using="user_id::text::uuid",
    )

    # восстанавливаем старый FK
    op.create_foreign_key(
        "resources_user_id_fkey",
        "resources",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )