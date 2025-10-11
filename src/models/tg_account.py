# src/models/tg_account.py
import uuid
from sqlalchemy import ForeignKey
from sqlalchemy import Text, DateTime, Boolean, BigInteger, Integer, Enum, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from src.app.core.db import Base  # твой Base уже есть :contentReference[oaicite:7]{index=7}

StatusEnum = Enum("new", "active", "paused", "blocked", "invalid", name="tg_account_status")
ReplyPolicyEnum = Enum("dm_only", "mentions_only", "read_only", name="tg_account_reply_policy")

class TgAccount(Base):
    __tablename__ = "tg_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    label: Mapped[str] = mapped_column(Text, nullable=False)
    phone_e164: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    tg_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    username: Mapped[str | None] = mapped_column(Text)
    owner_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    app_id: Mapped[int] = mapped_column(Integer, nullable=False)
    app_hash: Mapped[str] = mapped_column(Text, nullable=False)

    string_session: Mapped[str] = mapped_column(Text, nullable=False)  # шифруем на уровне приложения

    status: Mapped[str] = mapped_column(StatusEnum, nullable=False, default="new", server_default="new")
    reply_policy: Mapped[str] = mapped_column(ReplyPolicyEnum, nullable=False, default="dm_only", server_default="dm_only")

    twofa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    last_login_at: Mapped["DateTime"] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped["DateTime"] = mapped_column(DateTime(timezone=True))
    session_updated_at: Mapped["DateTime"] = mapped_column(DateTime(timezone=True))

    created_at: Mapped["DateTime"] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped["DateTime"] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
