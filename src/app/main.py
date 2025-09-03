# src/app/main.py
from pathlib import Path
import os
import sys

from datetime import datetime, timezone
from src.models.tg_account import TgAccount

from typing import Optional

from fastapi import FastAPI, Request, Depends, Form, UploadFile, File, HTTPException, status
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

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError

from telethon.errors import PhoneNumberInvalidError, FloodWaitError, ApiIdInvalidError


BASE_DIR = Path(__file__).resolve().parent
# глобальный словарь для временных клиентов Telethon
tg_clients: dict[str, TelegramClient] = {}
# если нужно обращаться к tg_user
sys.path.append(str(BASE_DIR.parent.parent / "tg_user"))

app = FastAPI(title="assistchat demo")
# ── ТРЕЙС АВТОРИЗАЦИИ В КОНСОЛЬ ────────────────────────────────────────────────
@app.middleware("http")
async def _authflow_trace(request, call_next):
    path = request.url.path
    watch = path.startswith(("/auth", "/profile", "/api/auth"))
    if watch:
        try:
            sess_keys = list(getattr(request, "session", {}).keys())
        except Exception:
            sess_keys = []
        print(
            "[IN]", request.method, path,
            "host=", request.headers.get("host"),
            "xfp=", request.headers.get("x-forwarded-proto"),
            "cookie=", request.headers.get("cookie"),
            "sess_keys=", sess_keys,
        )
    resp = await call_next(request)
    if watch:
        sc = resp.headers.get("set-cookie", "")
        print(
            "[OUT]", request.method, path,
            "status=", resp.status_code,
            "location=", resp.headers.get("location"),
            "set-cookie(session)=", ("assistchat_session" in sc),
        )
    return resp


# ────────────────────────────────────────────────────────────────────────────────
# Сессии (cookie) и шаблоны/статика
# ────────────────────────────────────────────────────────────────────────────────

@app.get("/login", include_in_schema=False)
async def login_alias():
    return RedirectResponse(url="/auth/login", status_code=302)


SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret-change-me")
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="assistchat_session",
    https_only=False,      # для localhost без HTTPS
    same_site="lax",       # для обычной навигации
    max_age=60 * 60 * 24 * 7,
    domain=None,           # без домена на localhost
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

# Доступ к /tables только для ADMIN
def require_admin(request: Request, db: SASession = Depends(get_db)) -> User:
    user = get_current_user(request, db)
    if not user:
        # не залогинен → 401 Unauthorized
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="UNAUTHORIZED"
        )
    role_val = user.role.value if hasattr(user.role, "value") else str(user.role)
    if role_val != "admin":
        # если роль не admin → прячем роут (404 Not Found)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="NOT_FOUND"
        )
    return user



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
    base = os.getenv("DOMAIN_NAME")
    if not base:
        raise RuntimeError("DOMAIN_NAME must be set in .env")
    return f"{base.rstrip('/')}{path}"

@app.get("/auth/google", include_in_schema=False)
async def auth_google(request: Request):
    # кука могла раздуться из-за множества _state_google_* → очистим перед новым заходом
    request.session.clear()
    return await oauth.google.authorize_redirect(
        request, redirect_uri=_redirect_uri("/auth/google/callback")
    )

@app.get("/auth/google/callback", include_in_schema=False)
async def auth_google_callback(request: Request, db: SASession = Depends(get_db)):
    token = await oauth.google.authorize_access_token(request)

    # Надёжно получаем email: сперва из id_token, иначе из userinfo
    # Сначала берём из id_token, но вызываем parse_id_token ТОЛЬКО если он есть
    # Берём данные напрямую из /userinfo (устраняем падение на parse_id_token)
    claims = await oauth.google.userinfo(token=token)

    email = claims.get("email")
    if not email:
        return JSONResponse({"ok": False, "error": "NO_EMAIL"}, status_code=400)

    username = claims.get("name") or email.split("@")[0]

    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user:
        # для OAuth-аккаунтов кладём пустую строку, чтобы пройти NOT NULL
        user = User(username=username, email=email, role=RoleEnum.USER,
                    hashed_password="", is_active=True)
        db.add(user);
        db.commit();
        db.refresh(user)

    request.session.clear()
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    request.session["role"] = getattr(user.role, "value", str(user.role))
    return RedirectResponse(url="/profile", status_code=303)


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
async def tables(request: Request, _: User = Depends(require_admin)):
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


# API: tg toggle (active <-> paused, с валидацией string_session)
@app.post("/api/toggle")
async def toggle_account(request: Request, db: SASession = Depends(get_db)):
    data = await request.json()
    phone = (data.get("phone") or "").strip()
    if not phone:
        raise HTTPException(status_code=400, detail="PHONE_REQUIRED")

    acc = db.execute(select(TgAccount).where(TgAccount.phone_e164 == phone)).scalars().first()
    if not acc:
        raise HTTPException(status_code=404, detail="ACCOUNT_NOT_FOUND")
    # доступ: владелец или админ
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="UNAUTHORIZED")
    role_val = user.role.value if hasattr(user.role, "value") else str(user.role)
    if role_val != "admin" and acc.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="FORBIDDEN")

    # Заблокированные/некорректные не трогаем
    if acc.status in ("blocked", "invalid"):
        return JSONResponse({"status": acc.status, "error": "LOCKED_STATUS"})

    now = datetime.now(timezone.utc)

    # active -> paused ; new/paused -> active (если есть валидная сессия)
    if acc.status == "active":
        acc.status = "paused"
    else:
        if not acc.string_session or len(acc.string_session) < 50:
            raise HTTPException(status_code=400, detail="NO_SESSION")
        acc.status = "active"
        acc.session_updated_at = now

    acc.updated_at = now
    db.add(acc)
    db.commit()
    return JSONResponse({"status": acc.status})


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

@app.get("/api/my/sessions")
async def api_my_sessions(request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    role_val = user.role.value if hasattr(user.role, "value") else str(user.role)

    q = select(
        TgAccount.id,
        TgAccount.label,
        TgAccount.phone_e164,
        TgAccount.status,
        TgAccount.tg_user_id,
        TgAccount.username,
        TgAccount.session_updated_at,
        TgAccount.last_login_at,
        TgAccount.last_seen_at,
        TgAccount.created_at,
    ).order_by(TgAccount.created_at.desc())

    if role_val != "admin":
        q = q.where(TgAccount.owner_user_id == user.id)

    rows = db.execute(q).all()

    data = []
    for r in rows:
        m = r._mapping
        data.append({
            "id": str(m["id"]),
            "label": m["label"],
            "phone": m["phone_e164"],
            "status": m["status"],
            "tg_user_id": m["tg_user_id"],
            "username": m["username"],
            "session_updated_at": m["session_updated_at"].isoformat() if m["session_updated_at"] else None,
            "last_login_at": m["last_login_at"].isoformat() if m["last_login_at"] else None,
            "last_seen_at": m["last_seen_at"].isoformat() if m["last_seen_at"] else None,
            "created_at": m["created_at"].isoformat() if m["created_at"] else None,
        })

    return {"ok": True, "items": data}


@app.post("/api/tg/send_code")
async def api_tg_send_code(payload: dict, request: Request, db: SASession = Depends(get_db)):
    """
    Шаг 1: сохраняем/обновляем запись tg_accounts (label, phone, api_id, api_hash, owner_user_id),
    отправляем код через Telethon, возвращаем ok либо detail с ошибкой.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False, "detail": "UNAUTHORIZED"}, status_code=401)

    label = (payload.get("label") or "").strip()
    phone = (payload.get("phone") or "").strip()
    api_id = int(payload.get("api_id") or 0)
    api_hash = (payload.get("api_hash") or "").strip()

    if not label or not phone or not api_id or not api_hash:
        return JSONResponse({"ok": False, "detail": "EMPTY_FIELDS"}, status_code=400)

    # upsert в tg_accounts по телефону
    acc = db.execute(
        select(TgAccount).where(TgAccount.phone_e164 == phone)
    ).scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if acc is None:
        acc = TgAccount(
            label=label,
            phone_e164=phone,
            app_id=api_id,
            app_hash=api_hash,
            owner_user_id=user.id,
            string_session="placeholder",
            status="new",
            created_at=now,
            updated_at=now,
            last_seen_at=now,
            session_updated_at=now,
            last_login_at=now,
        )
        db.add(acc)
        db.commit()
        db.refresh(acc)
    else:
        # обновим мета-данные, если изменились
        changed = False
        if acc.label != label:
            acc.label = label; changed = True
        if acc.app_id != api_id:
            acc.app_id = api_id; changed = True
        if acc.app_hash != api_hash:
            acc.app_hash = api_hash; changed = True
        if acc.owner_user_id != user.id:
            acc.owner_user_id = user.id; changed = True
        if changed:
            acc.updated_at = now
            db.add(acc); db.commit()

    # Отправка кода. В ЭТОЙ версии Telethon параметров type/current_number НЕТ.
    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            sent = await client.send_code_request(phone)
            print("[SEND_CODE][RAW]", repr(sent), file=sys.stderr, flush=True)
            print("[SEND_CODE][DICT]", sent.to_dict() if hasattr(sent, "to_dict") else "no to_dict", file=sys.stderr,
                  flush=True)
            print("[SEND_CODE][HASH_RAW]", repr(getattr(sent, "phone_code_hash", None)),
                  type(getattr(sent, "phone_code_hash", None)), file=sys.stderr, flush=True)

        else:
            return JSONResponse({"ok": False, "detail": "ALREADY_AUTHORIZED"}, status_code=400)

        print(
            "[SEND_CODE]",
            "phone=", phone,
            "phone_code_hash=", sent.phone_code_hash,
            "len=", len(sent.phone_code_hash),
            file=sys.stderr,
            flush=True
        )

        tg_clients[phone] = client
        request.session["tg_onboard"] = {
            "label": label,
            "phone": phone,
            "api_id": api_id,
            "api_hash": api_hash,
        }
    except ApiIdInvalidError:
        await client.disconnect()
        return JSONResponse({"ok": False, "detail": "API_ID_OR_HASH_INVALID"}, status_code=400)
    except PhoneNumberInvalidError:
        await client.disconnect()
        return JSONResponse({"ok": False, "detail": "PHONE_INVALID"}, status_code=400)
    except FloodWaitError as e:
        await client.disconnect()
        return JSONResponse({"ok": False, "detail": f"FLOOD_WAIT_{getattr(e, 'seconds', 'UNKNOWN')}"}, status_code=429)
    except Exception as e:
        await client.disconnect()
        return JSONResponse({"ok": False, "detail": "SEND_CODE_FAILED"}, status_code=500)

    # await client.disconnect()
    return {"ok": True}


@app.post("/api/tg/add")
async def api_tg_add(payload: dict, request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    label = (payload.get("label") or "").strip()
    phone = (payload.get("phone") or "").strip()
    app_id = payload.get("app_id")
    app_hash = (payload.get("app_hash") or "").strip()
    string_session = (payload.get("string_session") or "").strip()

    if not label or not phone or not app_id or not app_hash or not string_session or len(string_session) < 50:
        return JSONResponse({"ok": False, "error": "VALIDATION"}, status_code=400)

    now = datetime.now(timezone.utc)

    acc = db.execute(select(TgAccount).where(TgAccount.phone_e164 == phone)).scalars().first()
    if acc:
        # запрет на захват чужого номера
        if acc.owner_user_id and acc.owner_user_id != user.id:
            return JSONResponse({"ok": False, "error": "PHONE_TAKEN"}, status_code=409)
        acc.label = label
        acc.app_id = int(app_id)
        acc.app_hash = app_hash
        acc.string_session = string_session
        acc.owner_user_id = user.id
        acc.updated_at = now
        # мягко останавливаем; запуск — вручную кнопкой
        if acc.status == "new":
            acc.status = "paused"
        db.add(acc)
        db.commit()
        return {"ok": True}

    # создание новой записи
    acc = TgAccount(
        label=label,
        phone_e164=phone,
        app_id=int(app_id),
        app_hash=app_hash,
        string_session=string_session,
        owner_user_id=user.id,
        status="paused",
        last_login_at=now,
        last_seen_at=now,
        session_updated_at=now,
        updated_at=now,
    )
    db.add(acc)
    db.commit()
    return {"ok": True}


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

# ────────────────────────────────────────────────────────────────────────────────
# TG: страница
# ────────────────────────────────────────────────────────────────────────────────
@app.get("/tg", response_class=HTMLResponse)
async def tg_page(request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=302)
    return templates.TemplateResponse("tg.html", {
        "request": request,
        "username": user.username,
        "role": user.role.value if hasattr(user.role, "value") else str(user.role),
    })



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


@app.post("/api/tg/confirm")
async def api_tg_confirm(payload: dict, request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="UNAUTHORIZED")

    sdata = request.session.get("tg_onboard") or {}
    if not sdata:
        raise HTTPException(status_code=400, detail="NO_SEND_CODE")

    phone = (payload.get("phone") or "").strip()
    code = (payload.get("code") or "").strip()
    twofa = (payload.get("twofa") or "").strip()
    if not phone or not code:
        raise HTTPException(status_code=400, detail="EMPTY_FIELDS")

    if phone != sdata.get("phone"):
        raise HTTPException(status_code=400, detail="PHONE_MISMATCH")

    api_id = int(sdata["api_id"])
    api_hash = sdata["api_hash"]
    phone_code_hash = sdata.get("phone_code_hash")
    label = sdata["label"]

    client = tg_clients.pop(phone, None)
    if not client:
        raise HTTPException(status_code=400, detail="NO_CLIENT")

    try:
        print(
            "[CONFIRM]",
            "phone=", phone,
            "code=", code,
            "twofa=", "***" if twofa else "none",
            file=sys.stderr,
            flush=True
        )

        try:
            await client.sign_in(phone=phone, code=code)
        except SessionPasswordNeededError:
            if not twofa:
                raise HTTPException(status_code=400, detail="2FA_REQUIRED")
            await client.sign_in(password=twofa)

        me = await client.get_me()
        string_session = client.session.save()

        now = datetime.now(timezone.utc)
        # вставка/обновление записи
        existing = db.execute(
            select(TgAccount).where(TgAccount.phone_e164 == phone)
        ).scalar_one_or_none()

        if existing:
            # перезапишем поля и привяжем владельца
            existing.label = label
            existing.app_id = api_id
            existing.app_hash = api_hash
            existing.string_session = string_session
            existing.tg_user_id = int(getattr(me, "id", 0) or 0)
            existing.username = getattr(me, "username", None)
            existing.owner_user_id = user.id
            existing.status = "paused"            # по умолчанию выключена
            existing.last_login_at = now
            existing.updated_at = now
            db.add(existing)
        else:
            obj = TgAccount(
                label=label,
                phone_e164=phone,
                tg_user_id=int(getattr(me, "id", 0) or 0),
                username=getattr(me, "username", None),
                owner_user_id=user.id,
                app_id=api_id,
                app_hash=api_hash,
                string_session=str(string_session),
                status="paused",
                last_login_at=now,
                created_at=now,
                updated_at=now,
            )
            db.add(obj)

        db.commit()
        # очистим временные данные шага 1
        request.session.pop("tg_onboard", None)
        return {"ok": True}
    except PhoneCodeInvalidError:
        raise HTTPException(status_code=400, detail="CODE_INVALID")
    except PhoneCodeExpiredError:
        raise HTTPException(status_code=400, detail="CODE_EXPIRED")
    finally:
        # отключаем клиента, когда шаг завершён
        if client:
            await client.disconnect()