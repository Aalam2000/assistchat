"""add embedding vector to messages

Revision ID: a1b2c3d4e5f6
Revises: 214eb7dd1ee4
Create Date: 2026-06-12

"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from src.models.message import EMBEDDING_DIM

revision = "a1b2c3d4e5f6"
down_revision = "214eb7dd1ee4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column(
        "messages",
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_messages_embedding_hnsw "
        "ON messages USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_messages_embedding_hnsw")
    op.drop_column("messages", "embedding")
