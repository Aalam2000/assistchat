"""add owner_user_id to tg_accounts

Revision ID: c4af6c51f292
Revises: 70a3c3c0406a
Create Date: 2025-08-31 11:24:37.840081

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c4af6c51f292'
down_revision = '70a3c3c0406a'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("tg_accounts", sa.Column("owner_user_id", sa.Integer(), nullable=True))
    op.create_index("ix_tg_accounts_owner_user_id", "tg_accounts", ["owner_user_id"])
    op.create_foreign_key(
        "fk_tg_accounts_owner_user",
        "tg_accounts", "users",
        ["owner_user_id"], ["id"],
        ondelete="SET NULL",
    )

def downgrade() -> None:
    op.drop_constraint("fk_tg_accounts_owner_user", "tg_accounts", type_="foreignkey")
    op.drop_index("ix_tg_accounts_owner_user_id", table_name="tg_accounts")
    op.drop_column("tg_accounts", "owner_user_id")