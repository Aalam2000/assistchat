# src/models/prompt.py
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Text, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from src.common.db import Base

class Prompt(Base):
    __tablename__ = "prompts"

    # В БД PK = VARCHAR(36)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # В БД user_id = INTEGER (а не UUID)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # В БД title = TEXT (тип), обычно NOT NULL
    title: Mapped[str] = mapped_column(Text, nullable=False)

    # В БД body = NOT NULL
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # В БД params = JSONB NOT NULL
    params: Mapped[dict] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    # В БД updated_at = NOT NULL
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
