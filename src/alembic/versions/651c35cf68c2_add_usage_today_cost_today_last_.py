"""add usage_today cost_today last_activity error_message to resources

Revision ID: 651c35cf68c2
Revises: e1c266b5e787
Create Date: 2025-10-14 19:39:59.658149

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '651c35cf68c2'
down_revision = 'e1c266b5e787'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('resources', sa.Column('usage_today', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('resources', sa.Column('cost_today', sa.Float(),   nullable=False, server_default='0'))
    op.add_column('resources', sa.Column('last_activity', sa.DateTime(timezone=True), nullable=True))
    op.add_column('resources', sa.Column('error_message', sa.Text(), nullable=True))

def downgrade():
    op.drop_column('resources', 'error_message')
    op.drop_column('resources', 'last_activity')
    op.drop_column('resources', 'cost_today')
    op.drop_column('resources', 'usage_today')