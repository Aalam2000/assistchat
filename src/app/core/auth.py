"""
src/app/core/auth.py — функции авторизации и управления пользователями.
Содержит получение текущего пользователя, проверку роли и работу с паролями.
"""

from fastapi import Request, Depends, HTTPException, status
from sqlalchemy.orm import Session
from src.models.user import User
from src.app.core.db import get_db
from src.app.core.config import pwd_context

def get_current_user(request: Request, db: Session = Depends(get_db)):
    """
    Возвращает текущего пользователя по session['user_id'].
    Если пользователь не авторизован — возвращает None.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get(User, user_id)

def require_admin(request: Request, db: Session = Depends(get_db)) -> User:
    """
    Проверяет, что текущий пользователь имеет роль ADMIN.
    Если не авторизован — 401.
    Если не админ — 404 (для сокрытия маршрута).
    """
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="UNAUTHORIZED")
    role_val = user.role.value if hasattr(user.role, "value") else str(user.role)
    if role_val != "admin":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_FOUND")
    return user

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Проверяет соответствие введённого пароля сохранённому хэшу.
    Возвращает True при совпадении.
    """
    if not hashed_password:
        return False
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False

def hash_password(plain_password: str) -> str:
    """
    Хэширует пароль с помощью bcrypt.
    Возвращает строку-хэш.
    """
    return pwd_context.hash(plain_password)
