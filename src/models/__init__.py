# src/models/__init__.py
from src.common.db import Base
from .user import User, RoleEnum
from .tg_account import TgAccount
from .message import Message
# если есть еще модели (updates_seen и пр.), тоже импортируем
