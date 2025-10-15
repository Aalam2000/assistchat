# src/models/resource.py
import uuid

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.sql import func

from src.app.core.db import Base


class Resource(Base):
    __tablename__ = "resources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    provider = Column(String(50), nullable=False)  # telegram | avito | flru | voice | ...
    label = Column(Text, nullable=False)

    status = Column(String(20), nullable=False, default="new")  # new|active|paused|error|blocked
    phase = Column(String(20), nullable=False, default="ready")  # ready|starting|running|error|paused

    last_error_code = Column(String(50))
    last_checked_at = Column(DateTime(timezone=True))

    meta_json = Column(MutableDict.as_mutable(JSONB), default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    # учёт и метрики для провайдеров
    usage_today = Column(Integer, nullable=False, server_default="0")  # кол-во токенов за сегодня
    cost_today = Column(Float, nullable=False, server_default="0")  # стоимость за сегодня

    last_activity = Column(DateTime(timezone=True))  # последняя активность провайдера
    error_message = Column(Text)
