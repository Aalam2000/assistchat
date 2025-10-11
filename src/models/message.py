from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Text, BigInteger, Integer, DateTime, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from src.app.core.db import Base

class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 🔄 заменили account_id → resource_id
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False
    )

    peer_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    peer_type: Mapped[str] = mapped_column(Text, nullable=False)
    chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    msg_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    direction: Mapped[str] = mapped_column(Text, nullable=False)  # in|out
    msg_type: Mapped[str] = mapped_column(Text, nullable=False)   # text|voice|file
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    tokens_in: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    service_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    external_chat_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    external_msg_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
