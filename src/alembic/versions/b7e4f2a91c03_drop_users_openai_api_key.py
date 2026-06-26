"""drop users.openai_api_key

Revision ID: b7e4f2a91c03
Revises: a1b2c3d4e5f6
Create Date: 2026-06-26

"""
from alembic import op
import sqlalchemy as sa

revision = "b7e4f2a91c03"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("users", "openai_api_key")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("openai_api_key", sa.Text(), nullable=True),
    )
