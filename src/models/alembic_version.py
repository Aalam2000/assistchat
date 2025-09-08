from __future__ import annotations
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String
from src.common.db import Base

class AlembicVersion(Base):
    __tablename__ = "alembic_version"
    version_num: Mapped[str] = mapped_column(String(32), primary_key=True)
