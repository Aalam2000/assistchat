# src/models/user.py
from sqlalchemy import Column, Integer, String, DateTime, func, Boolean, Enum, Text
from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column

from enum import Enum as PyEnum
from src.app.core.db import Base

class RoleEnum(PyEnum):
    ADMIN = "admin"
    USER = "user"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=True)
    role = Column(Enum(RoleEnum), nullable=False, default=RoleEnum.USER)
    hashed_password = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    openai_api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bot_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
