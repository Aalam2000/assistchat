# src/models/service_account.py
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Text, Integer, DateTime, String, LargeBinary
from sqlalchemy.dialects.postgresql import JSONB
from src.common.db import Base

class ServiceAccount(Base):
    __tablename__ = "service_accounts"

    # id = VARCHAR(36)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # user_id = INTEGER
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # provider = TEXT NOT NULL
    provider: Mapped[str] = mapped_column(Text, nullable=False)

    # label = TEXT NOT NULL
    label: Mapped[str] = mapped_column(Text, nullable=False)

    # credentials_enc = BYTEA
    credentials_enc: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)

    # prompt_id = VARCHAR(36)
    prompt_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    # ↓ как в БД
    external_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
