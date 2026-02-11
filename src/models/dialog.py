from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import Text, BigInteger, DateTime, String, ForeignKey, Integer, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func, text

from src.app.core.db import Base


class Dialog(Base):
    __tablename__ = "dialogs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )

    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
    )

    thread_key: Mapped[str] = mapped_column(Text, nullable=False)

    peer_type: Mapped[str] = mapped_column(Text, nullable=False)
    peer_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    # Срезы LangGraph/RLM (фиксированный набор)
    graph_state: Mapped[Dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB), nullable=False, server_default=text("'{}'::jsonb"), default=dict
    )
    summary: Mapped[Dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB), nullable=False, server_default=text("'{}'::jsonb"), default=dict
    )
    facts: Mapped[Dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB), nullable=False, server_default=text("'{}'::jsonb"), default=dict
    )
    rag_cache: Mapped[Dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB), nullable=False, server_default=text("'{}'::jsonb"), default=dict
    )
    flags: Mapped[Dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB), nullable=False, server_default=text("'{}'::jsonb"), default=dict
    )

    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # relations
    messages = relationship("Message", back_populates="dialog", passive_deletes=False)

    __table_args__ = (
        UniqueConstraint("resource_id", "thread_key", name="uq_dialogs_resource_thread_key"),
        Index("ix_dialogs_resource_last_message_at", "resource_id", "last_message_at"),
        Index("ix_dialogs_resource_peer", "resource_id", "peer_id"),
    )
