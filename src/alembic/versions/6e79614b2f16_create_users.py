"""create users

Revision ID: 6e79614b2f16
Revises: 38ab48e15002
Create Date: 2025-08-22 11:13:28.855710


"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "6e79614b2f16"
down_revision = "38ab48e15002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Таблица пользователей (подгони поля при необходимости под свою модель)
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.String(50), nullable=False, unique=True),
        sa.Column("email", sa.String(255), nullable=True, unique=True),
        sa.Column("role", sa.String(50), nullable=False, server_default="user"),
        sa.Column("hashed_password", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # 2) Новые поля в messages — в безопасном порядке
    # 2.1 author: добавляем как NOT NULL с временным дефолтом, чтобы прошли старые строки
    op.add_column(
        "messages",
        sa.Column("author", sa.Text(), nullable=False, server_default=sa.text("'system'")),
    )

    # 2.2 content: сначала nullable=True, потом заполним и сделаем NOT NULL
    op.add_column("messages", sa.Column("content", sa.Text(), nullable=True))

    # 2.3 status/ts: NOT NULL c дефолтами сразу — для старых и новых строк
    op.add_column("messages", sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'new'")))
    op.add_column(
        "messages",
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # 3) Бэкофилл контента из старого поля text (если оно есть)
    #    Если столбца text в этой БД не было — UPDATE просто ничего не изменит, это нормально.
    op.execute("UPDATE messages SET content = text WHERE content IS NULL AND text IS NOT NULL")

    # 4) Делаем content NOT NULL после заполнения
    op.alter_column("messages", "content", existing_type=sa.Text(), nullable=False)

    # 5) Снимаем временный дефолт с author, чтобы новые записи заполнялись явно
    op.alter_column("messages", "author", server_default=None)


def downgrade() -> None:
    # Откатываем в обратном порядке
    op.drop_column("messages", "ts")
    op.drop_column("messages", "status")
    op.drop_column("messages", "content")
    op.drop_column("messages", "author")
    op.drop_table("users")
