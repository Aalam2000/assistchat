from __future__ import annotations
import uuid
from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import DateTime, BigInteger
from sqlalchemy.dialects.postgresql import UUID
from src.common.db import Base

class UpdateSeen(Base):
    __tablename__ = "updates_seen"

    # Композитный PK: (account_id, chat_id, message_id)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    message_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
