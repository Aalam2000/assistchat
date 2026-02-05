"""
src/app/routes/auth_routes.py - Маршруты авторизации: регистрация, логин, logout, Google OAuth, информация о текущем пользователе.
"""
from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session as SASession
from authlib.integrations.starlette_client import OAuth
from passlib.context import CryptContext
from src.models.user import User, RoleEnum
from src.app.core.db import get_db
from src.app.core.auth import get_current_user
import os

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Настройка Google OAuth
oauth = OAuth()
oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


def verify_password(plain_password: str, hashed_password: str | None) -> bool:
    """Проверяет пароль пользователя."""
    if not hashed_password:
        return False
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


def hash_password(plain_password: str) -> str:
    """Хэширует пароль."""
    return pwd_context.hash(plain_password)


def _redirect_uri(path: str = "/auth/google/callback") -> str:
    """Формирует корректный redirect URI для OAuth."""
    base = os.getenv("DOMAIN_NAME")
    if not base:
        raise RuntimeError("DOMAIN_NAME must be set in .env")
    return f"{base.rstrip('/')}{path}"


# --- ROUTES ----------------------------------------------------------

@router.get("/auth/google", include_in_schema=False)
async def auth_google(request: Request):
    """Старт авторизации через Google."""
    request.session.clear()
    request.session["next"] = request.headers.get("referer", "/")
    redirect_uri = str(request.url_for("auth_google_callback"))
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/auth/google/callback", include_in_schema=False)
async def auth_google_callback(request: Request, db: SASession = Depends(get_db)):
    """Callback от Google OAuth → создаёт или восстанавливает пользователя."""
    token = await oauth.google.authorize_access_token(request)
    claims = await oauth.google.userinfo(token=token)
    email = claims.get("email")
    if not email:
        return JSONResponse({"ok": False, "error": "NO_EMAIL"}, status_code=400)

    username = claims.get("name") or email.split("@")[0]
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user:
        user = User(username=username, email=email, role=RoleEnum.USER,
                    hashed_password="", is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)

    request.session.update({
        "user_id": user.id,
        "username": user.username,
        "role": getattr(user.role, "value", str(user.role))
    })
    return RedirectResponse(url="/", status_code=303)


@router.post("/api/auth/register")
async def api_auth_register(payload: dict, request: Request, db: SASession = Depends(get_db)):
    """Регистрация нового пользователя с автологином."""
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    email = (payload.get("email") or "").strip() or None
    if not username or not password:
        return JSONResponse({"ok": False, "error": "EMPTY_FIELDS"}, status_code=400)

    exists = db.execute(select(User).where(User.username == username)).first()
    if exists:
        return JSONResponse({"ok": False, "error": "USER_EXISTS"}, status_code=409)

    new_user = User(
        username=username,
        email=email,
        role=RoleEnum.USER,
        hashed_password=hash_password(password),
        is_active=True
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    request.session.update({
        "user_id": new_user.id,
        "username": new_user.username,
        "role": new_user.role.value
    })
    return {"ok": True, "redirect": "/profile"}


@router.post("/api/auth/login")
async def api_auth_login(payload: dict, request: Request, db: SASession = Depends(get_db)):
    """Авторизация по логину/паролю."""
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    if not username or not password:
        return JSONResponse({"ok": False, "error": "EMPTY_FIELDS"}, status_code=400)

    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_password):
        return JSONResponse({"ok": False, "error": "INVALID_CREDENTIALS"}, status_code=401)

    request.session.clear()
    request.session.update({
        "user_id": user.id,
        "username": user.username,
        "role": getattr(user.role, "value", str(user.role))
    })
    return {"ok": True}


@router.post("/api/auth/logout")
async def api_auth_logout(request: Request):
    """Выход из системы (очистка сессии и сброс cookie)."""
    request.session.clear()
    response = JSONResponse({"ok": True, "redirect": "/"})
    # Удаляем cookie, чтобы браузер забыл старую сессию
    response.delete_cookie("session")
    return response



@router.get("/api/auth/me")
async def api_auth_me(request: Request, db: SASession = Depends(get_db)):
    """Возвращает данные текущего пользователя."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    return {
        "ok": True,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": getattr(user.role, "value", str(user.role)),
            "is_active": user.is_active,
        },
    }
