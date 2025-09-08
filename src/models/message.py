from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Text, BigInteger, Integer, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from src.common.db import Base

class Message(Base):
    __tablename__ = "messages"

    # PK
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ↓ как в БД по твоему отчёту check_models
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    peer_id: Mapped[int] = mapped_column(BigInteger, nullable=False)      # было nullable=True → в БД NOT NULL
    peer_type: Mapped[str] = mapped_column(Text, nullable=False)          # было VARCHAR, nullable=True → TEXT, NOT NULL
    chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    msg_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    direction: Mapped[str] = mapped_column(Text, nullable=False)          # было VARCHAR, nullable=True → TEXT, NOT NULL
    msg_type: Mapped[str] = mapped_column(Text, nullable=False)           # было VARCHAR, nullable=True → TEXT, NOT NULL
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tokens_in: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    service_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(Text, nullable=True)          # тип в БД TEXT
    external_chat_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # тип в БД TEXT
    external_msg_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # тип в БД TEXT
