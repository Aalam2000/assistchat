from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Text, BigInteger, Integer, DateTime, String, ForeignKey, Boolean, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.sql import func
from sqlalchemy import text as sa_text

from src.app.core.db import Base


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
    )

    # NEW
    dialog_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dialogs.id", ondelete="SET NULL"),
        nullable=True,
    )

    peer_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    peer_type: Mapped[str] = mapped_column(Text, nullable=False)
    chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    msg_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    direction: Mapped[str] = mapped_column(Text, nullable=False)  # in|out
    msg_type: Mapped[str] = mapped_column(Text, nullable=False, server_default=sa_text("'text'::text"))  # text|voice|file
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    tokens_in: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # NEW (технические сообщения графа/инструментов)
    is_internal: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_text("false"))

    # NEW (prompt_id, api_keys_resource_id, api_key_field, model, timings, usage...)
    meta_json: Mapped[Dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB),
        nullable=False,
        server_default=sa_text("'{}'::jsonb"),
        default=dict,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    service_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    external_chat_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    external_msg_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    dialog = relationship("Dialog", back_populates="messages")

    __table_args__ = (
        # есть в БД
        Index("ix_messages_service_created", "service_id", "created_at"),

        # новые под диалоги/историю
        Index("ix_messages_dialog_created_at", "dialog_id", "created_at"),
        Index("ix_messages_resource_peer_created_at", "resource_id", "peer_id", "created_at"),

        # новая уникальность (в миграции заменим старую uq_messages_provider_chat_msg)
        UniqueConstraint(
            "provider", "resource_id", "external_chat_id", "external_msg_id",
            name="uq_messages_provider_resource_chat_msg",
        ),
    )
