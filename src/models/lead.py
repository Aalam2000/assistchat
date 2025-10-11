# src/models/lead.py
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Text, DateTime, String, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from src.app.core.db import Base

class Lead(Base):
    __tablename__ = "leads"

    # PK = VARCHAR(36)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # service_id = VARCHAR(36) NOT NULL
    service_id: Mapped[str] = mapped_column(String(36), nullable=False)

    # provider = TEXT NOT NULL
    provider: Mapped[str] = mapped_column(Text, nullable=False)

    # external_id = TEXT NOT NULL
    external_id: Mapped[str] = mapped_column(Text, nullable=False)

    # title = TEXT NULL
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # budget = NUMERIC(12,2) NULL
    budget: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)

    # customer_ref = TEXT NULL
    customer_ref: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # status = TEXT NOT NULL
    status: Mapped[str] = mapped_column(Text, nullable=False)

    # meta = JSONB NOT NULL
    meta: Mapped[dict] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
