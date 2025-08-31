"""add tg_accounts.status"""

from alembic import op
import sqlalchemy as sa

revision = "70a3c3c0406a"
down_revision = "6e79614b2f16"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE tg_accounts ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'inactive';")



def downgrade() -> None:
    op.drop_column("tg_accounts", "status")
