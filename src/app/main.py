# src/app/main.py
from pathlib import Path
import os
import sys
import asyncio
from typing import Optional

from fastapi import FastAPI, Request, Depends, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.responses import JSONResponse, StreamingResponse
from starlette.middleware.sessions import SessionMiddleware

import io, zipfile, tempfile
from scripts.QR import generate_qr_with_logo

from sqlalchemy import inspect, text, select
from sqlalchemy.orm import sessionmaker, Session as SASession

from passlib.context import CryptContext

from scripts import tg_user_dm_responder
from src.common.db import engine  # engine из вашего db.py/common/db.py
from src.models.user import User, RoleEnum

BASE_DIR = Path(__file__).resolve().parent

# если нужно обращаться к tg_user
sys.path.append(str(BASE_DIR.parent.parent / "tg_user"))

app = FastAPI(title="assistchat demo")

# --- GOOGLE OAUTH (минимум) ---
from authlib.integrations.starlette_client import OAuth

oauth = OAuth()
oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

def _redirect_uri(path: str = "/auth/google/callback") -> str:
    base = os.getenv("DOMAIN_NAME", "http://localhost:8000").rstrip("/")
    return f"{base}{path}"

@app.get("/auth/google", include_in_schema=False)
async def auth_google(request: Request):
    return await oauth.google.authorize_redirect(request, redirect_uri=_redirect_uri())

@app.get("/auth/google/callback", include_in_schema=False)
async def auth_google_callback(request: Request):
    return RedirectResponse("/profile", status_code=302)



# ────────────────────────────────────────────────────────────────────────────────
# Сессии (cookie) и шаблоны/статика
# ────────────────────────────────────────────────────────────────────────────────
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret-change-me")
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="assistchat_session",
    https_only=False,          # поставьте True за reverse-proxy/https
    same_site="lax",
    max_age=60 * 60 * 24 * 7,  # 7 дней
)

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static"
)
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Локальный sessionmaker (не полагаемся на внешние фабрики)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Пароли
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ────────────────────────────────────────────────────────────────────────────────
# Утилиты
# ────────────────────────────────────────────────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verify_password(plain_password: str, hashed_password: Optional[str]) -> bool:
    if not hashed_password:
        return False
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        # если формат не совпал — считаем невалидным
        return False

def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)

def get_current_user(request: Request, db: SASession) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get(User, user_id)

# ────────────────────────────────────────────────────────────────────────────────
# Публичные страницы
# ────────────────────────────────────────────────────────────────────────────────
@app.get("/tables", response_class=HTMLResponse)
async def tables(request: Request):
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    data = {}
    with engine.connect() as conn:
        for table in table_names:
            cols = [col["name"] for col in inspector.get_columns(table)]
            rows = conn.execute(text(f'SELECT * FROM "{table}"')).fetchall()
            data[table] = {"columns": cols, "rows": rows}

    return templates.TemplateResponse("index.html", {"request": request, "data": data})

@app.get("/health")
async def health():
    return "ok"

# ────────────────────────────────────────────────────────────────────────────────
# API: tg toggle (как было)
# ────────────────────────────────────────────────────────────────────────────────
@app.post("/api/toggle")
async def toggle_account(request: Request):
    data = await request.json()
    phone = data.get("phone")
    if not phone:
        return JSONResponse({"error": "phone required"}, status_code=400)

    new_status = tg_user_dm_responder.toggle_session(phone)
    return {"phone": phone, "status": new_status}

# ────────────────────────────────────────────────────────────────────────────────
# AUTH: страницы
# ────────────────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
@app.get("/auth/login", response_class=HTMLResponse)
async def auth_login_page(request: Request):
    # если уже залогинен — в профиль
    if request.session.get("user_id"):
        return RedirectResponse(url="/profile", status_code=302)
    return templates.TemplateResponse("auth/login.html", {"request": request})

# ────────────────────────────────────────────────────────────────────────────────
# AUTH: API (login/register/logout/me)
# ────────────────────────────────────────────────────────────────────────────────
@app.post("/api/auth/login")
async def api_auth_login(payload: dict, request: Request, db: SASession = Depends(get_db)):
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""

    if not username or not password:
        return JSONResponse({"ok": False, "error": "EMPTY_FIELDS"}, status_code=400)

    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if not user or not user.is_active:
        return JSONResponse({"ok": False, "error": "USER_NOT_FOUND_OR_INACTIVE"}, status_code=401)

    if not verify_password(password, user.hashed_password):
        return JSONResponse({"ok": False, "error": "BAD_CREDENTIALS"}, status_code=401)

    # set session
    request.session.update({
        "user_id": user.id,
        "username": user.username,
        "role": user.role.value if hasattr(user.role, "value") else str(user.role),
    })
    return {"ok": True, "redirect": "/profile"}

@app.post("/api/auth/register")
async def api_auth_register(payload: dict, request: Request, db: SASession = Depends(get_db)):
    # Регистрация открыта. Требует: username, password, email (необяз.)
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    email = (payload.get("email") or "").strip() or None

    if not username or not password:
        return JSONResponse({"ok": False, "error": "EMPTY_FIELDS"}, status_code=400)

    exists = db.execute(select(User).where((User.username == username) | (User.email == email))).first() if email else \
             db.execute(select(User).where(User.username == username)).first()
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

    # авто-логин
    request.session.update({
        "user_id": new_user.id,
        "username": new_user.username,
        "role": new_user.role.value
    })
    return {"ok": True, "redirect": "/profile"}

@app.post("/api/auth/logout")
async def api_auth_logout(request: Request):
    request.session.clear()
    return {"ok": True, "redirect": "/auth/login"}

@app.get("/api/auth/me")
async def api_auth_me(request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    return {
        "ok": True,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role.value if hasattr(user.role, "value") else str(user.role),
            "is_active": user.is_active
        }
    }

# ────────────────────────────────────────────────────────────────────────────────
# PROFILE
# ────────────────────────────────────────────────────────────────────────────────
@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=302)

    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "username": user.username,
            "role": user.role.value if hasattr(user.role, "value") else str(user.role),
        }
    )



# ────────────────────────────────────────────────────────────────────────────────
# QR: страница
# ────────────────────────────────────────────────────────────────────────────────
@app.get("/qr", response_class=HTMLResponse)
async def qr_page(request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=302)
    return templates.TemplateResponse("qr.html", {"request": request, "username": user.username})


@app.get("/ai", response_class=HTMLResponse)
def ai_page(request: Request):
    user = getattr(request.state, "user", None)
    ctx = {
        "request": request,
        "username": getattr(user, "username", "Гость"),
        "role": getattr(user, "role", "user"),
    }
    return templates.TemplateResponse("ai.html", ctx)



@app.get("/callcenter", response_class=HTMLResponse)
def callcenter_page(request: Request):
    user = getattr(request.state, "user", None)
    ctx = {
        "request": request,
        "username": getattr(user, "username", "Гость"),
        "role": getattr(user, "role", "user"),
    }
    return templates.TemplateResponse("callcenter.html", ctx)


# ────────────────────────────────────────────────────────────────────────────────
# QR: API генерации (ZIP из PNG+PDF)
# ────────────────────────────────────────────────────────────────────────────────
@app.post("/api/qr/build")
async def api_qr_build(text: str = Form(...), logo: UploadFile = File(...)):
    if logo.content_type not in {"image/png","image/tiff","image/x-tiff"}:
        return JSONResponse({"ok": False, "error": "LOGO_TYPE"}, status_code=400)
    with tempfile.TemporaryDirectory() as tmp:
        logo_path = f"{tmp}/{logo.filename}"
        with open(logo_path, "wb") as f:
            f.write(await logo.read())

        png_path, pdf_path = generate_qr_with_logo(
            url=text,
            logo_path=logo_path,
            out_dir=tmp,
            file_stem="qr_with_logo",
            qr_size_mm=30.0,
            dpi=300,
            logo_ratio=0.20,
            white_pad_mm=2.0,
            logo_has_alpha=True,
            try_knockout_white=False,
        )
        mem = io.BytesIO()
        with zipfile.ZipFile(mem, "w", compression=zipfile.ZIP_DEFLATED) as z:
            import os
            z.write(png_path, arcname=os.path.basename(png_path))
            z.write(pdf_path, arcname=os.path.basename(pdf_path))
        mem.seek(0)
        return StreamingResponse(mem, media_type="application/zip",
                                 headers={"X-File-Name":"qr_with_logo"})

