# src/models/service_rule.py
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Text, DateTime, String
from src.common.db import Base

class ServiceRule(Base):
    __tablename__ = "service_rules"

    # В БД id = VARCHAR(36)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # В БД service_id = VARCHAR(36)
    service_id: Mapped[str] = mapped_column(String(36), nullable=False)

    # В БД kind = TEXT NOT NULL
    kind: Mapped[str] = mapped_column(Text, nullable=False)

    # В БД target_type = TEXT NOT NULL
    target_type: Mapped[str] = mapped_column(Text, nullable=False)

    # В БД target_value = TEXT NOT NULL
    target_value: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    # внутри класса ServiceRule:
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
