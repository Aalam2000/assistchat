"""make meta_json mutable

Revision ID: e1c266b5e787
Revises: a066a6fe4d1b
Create Date: 2025-10-14 10:26:58.760662

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e1c266b5e787'
down_revision = 'a066a6fe4d1b'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.alter_column('resources', 'meta_json', type_=sa.dialects.postgresql.JSONB())

def downgrade() -> None:
    op.alter_column('resources', 'meta_json', type_=sa.JSON())

