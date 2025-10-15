"""add bot_enabled to users

Revision ID: a066a6fe4d1b
Revises: 0c7d905c79ff
Create Date: 2025-10-11 20:15:25.992389

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a066a6fe4d1b'
down_revision = '0c7d905c79ff'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('users', sa.Column('bot_enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')))

def downgrade():
    op.drop_column('users', 'bot_enabled')