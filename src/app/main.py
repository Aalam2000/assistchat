# src/app/main.py model:32
import io
import os
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID

# --- GOOGLE OAUTH (минимум) ---
from authlib.integrations.starlette_client import OAuth
from autoi18n import Translator
from fastapi import FastAPI, Request, Depends, Form, UploadFile, File, HTTPException, status, Body
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from sqlalchemy import inspect, text, select
from sqlalchemy.orm import Session as SASession
from starlette.middleware.sessions import SessionMiddleware

from scripts.QR import generate_qr_with_logo
from src.app.providers import PROVIDERS, validate_provider_meta
from src.common.db import SessionLocal  # если уже есть — пропусти
from src.common.db import engine
from src.models import Resource
from src.models.user import User, RoleEnum

import traceback
import time
import traceback
from telethon.errors import FloodWaitError, PhoneCodeInvalidError, PhoneNumberInvalidError

# --- TELEGRAM ACTIVATE (in-memory pending) ---
from telethon import TelegramClient
from telethon.sessions import StringSession

PENDING_TG: dict[str, dict] = {}  # rid -> {'client': TelegramClient, 'session': str, 'phone': str, 'app_id': int, 'app_hash': str, 'ts': float}
PENDING_TG_TTL = int(os.getenv("TG_ACT_TTL", "300"))  # секунд держим живую сессию до ввода кода

def _pending_drop(rid: str):
    """Снять клиента из кэша и разорвать соединение (тихо)."""
    entry = PENDING_TG.pop(rid, None)
    if not entry:
        return
    try:
        client = entry.get("client")
        if client:
            print(f"[TG_ACT][{rid}] pending_drop: disconnect")
            # client.disconnect() — coroutine; вызываем из корутины там, где знаем, что у нас есть loop
    except Exception as e:
        print(f"[TG_ACT][{rid}] pending_drop error:", repr(e))



tr = Translator(cache_dir="./translations")
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

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

SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret-change-me")
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="assistchat_session",
    https_only=False,  # для localhost без HTTPS
    same_site="lax",  # для обычной навигации
    max_age=60 * 60 * 24 * 7,
    domain=None,  # без домена на localhost
)

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static"
)

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

    return render_i18n("index.html", request, "tables_index", {"data": data})


@app.get("/health")
async def health():
    return "ok"


# ────────────────────────────────────────────────────────────────────────────────
# AUTH: страницы
# ────────────────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def root_redirect():
    return RedirectResponse(url="/auth/login", status_code=302)


@app.get("/auth/login", response_class=HTMLResponse)
async def auth_login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse(url="/profile", status_code=302)
    return render_i18n("auth/login.html", request, "auth_login", {})


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


@app.get("/api/providers")
def api_providers(request: Request):
    # Отдаём только то, что нужно UI: ключ, видимое имя, шаблон meta_json и (опц.) описание
    items = []
    for key, cfg in PROVIDERS.items():
        items.append({
            "key": key,
            "name": cfg.get("title", key),
            "template": cfg.get("template", {}),
            "help": cfg.get("help", {}),
        })
    return {"ok": True, "providers": items}


@app.get("/api/providers/{key}/schema")
def api_provider_schema(key: str):
    cfg = PROVIDERS.get(key)
    if not cfg:
        raise HTTPException(status_code=404, detail="UNKNOWN_PROVIDER")
    # для фронта удобно вернуть сразу и schema, и template, и help
    return {
        "ok": True,
        "schema": cfg.get("schema", {}),
        "template": cfg.get("template", {}),
        "help": cfg.get("help", {}),
    }


# ────────────────────────────────────────────────────────────────────────────────
# PROFILE
# ────────────────────────────────────────────────────────────────────────────────
@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=302)

    return render_i18n(
        "profile.html",
        request,
        "profile",
        {
            "username": user.username,
            "role": user.role.value if hasattr(user.role, "value") else str(user.role),
        }
    )


@app.get("/resources", response_class=HTMLResponse)
async def resources_page(request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=302)

    return render_i18n(
        "resources.html",
        request,
        "resources",
        {
            "username": user.username,
            "role": user.role.value if hasattr(user.role, "value") else str(user.role),
        }
    )


# ────────────────────────────────────────────────────────────────────────────────
# PROFILE: сводка статуса бота (устойчивая к отсутствию таблиц/колонок)
# ────────────────────────────────────────────────────────────────────────────────
@app.get("/api/status")
async def api_status(request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    rows = db.execute(
        select(Resource).where(Resource.user_id == user.id)
    ).scalars().all()

    services_total = len(rows)
    services_active = sum(1 for r in rows if r.status == "active")

    tg_total = sum(1 for r in rows if r.provider == "telegram")
    tg_active = sum(1 for r in rows if r.provider == "telegram" and r.status == "active")

    return {
        "ok": True,
        "on": services_active > 0,
        "services_active": services_active,
        "services_total": services_total,
        "tg_active": tg_active,
        "tg_total": tg_total,
    }


# ────────────────────────────────────────────────────────────────────────────────
# PROFILE: OpenAI настройки пользователя
# ────────────────────────────────────────────────────────────────────────────────

@app.get("/api/profile/openai")
async def api_profile_openai_get(request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    key = getattr(user, "openai_api_key", None)
    masked = None
    if key:
        masked = (key[:3] + "…" + key[-4:]) if len(key) > 7 else "******"

    # дефолты (пока без хранения отдельных полей)
    return {
        "ok": True,
        "mode": "byok" if key else "managed",
        "key_masked": masked,
        "model": "gpt-4o-mini",
        "history_limit": 20,
        "voice_enabled": False,
    }


@app.post("/api/profile/openai/test")
async def api_profile_openai_test(payload: dict, request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    mode = (payload.get("mode") or "byok").lower()
    if mode == "byok":
        key = (payload.get("key") or "").strip()
        # минимальная валидация формата, без внешних запросов
        if not key or not key.startswith("sk-") or len(key) < 20:
            return JSONResponse({"ok": False, "error": "KEY_FORMAT"}, status_code=400)

    return {"ok": True, "message": "Ок"}


@app.post("/api/profile/openai/save")
async def api_profile_openai_save(payload: dict, request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    mode = (payload.get("mode") or "byok").lower()
    if mode == "byok":
        user.openai_api_key = (payload.get("key") or "").strip() or None
    else:
        # managed-режим — ключ пользователя не храним
        user.openai_api_key = None

    db.add(user)
    db.commit()
    return {"ok": True}


# ────────────────────────────────────────────────────────────────────────────────
# QR: страница
# ────────────────────────────────────────────────────────────────────────────────
@app.get("/qr", response_class=HTMLResponse)
async def qr_page(request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=302)
    return render_i18n("qr.html", request, "qr", {"username": user.username})


@app.get("/ai", response_class=HTMLResponse)
def ai_page(request: Request):
    user = getattr(request.state, "user", None)
    ctx = {
        "request": request,
        "username": getattr(user, "username", "Гость"),
        "role": getattr(user, "role", "user"),
    }
    return render_i18n("ai.html", request, "ai", ctx)


@app.get("/callcenter", response_class=HTMLResponse)
def callcenter_page(request: Request):
    user = getattr(request.state, "user", None)
    ctx = {
        "request": request,
        "username": getattr(user, "username", "Гость"),
        "role": getattr(user, "role", "user"),
    }
    return render_i18n("callcenter.html", request, "callcenter", ctx)


# ────────────────────────────────────────────────────────────────────────────────
# QR: API генерации (ZIP из PNG+PDF)
# ────────────────────────────────────────────────────────────────────────────────
@app.post("/api/qr/build")
async def api_qr_build(text: str = Form(...), logo: UploadFile = File(...)):
    if logo.content_type not in {"image/png", "image/tiff", "image/x-tiff"}:
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
                                 headers={"X-File-Name": "qr_with_logo"})


# ── i18n: helpers ─────────────────────────────────────────────────────────────
def _get_lang(request: Request) -> str:
    lang = (request.cookies.get("lang") or "").lower()
    if lang in ("ru", "en"):
        return lang
    # язык из браузера, иначе RU по умолчанию
    return tr.detect_browser_lang(request.headers.get("accept-language", "")) or "ru"


def _inject_en_button(html: str, lang: str) -> str:
    cur = (lang or "ru").lower()
    label, href = ("RU", "/set-lang/ru") if cur.startswith("en") else ("EN", "/set-lang/en")

    if 'id="i18n-toggle"' in html:
        return html

    btn = (
        f'<a id="i18n-toggle" href="{href}" '
        'style="position:fixed;top:10px;right:10px;z-index:9999;'
        'padding:6px 10px;border:1px solid #aaa;border-radius:8px;'
        'background:#fff;opacity:.95;text-decoration:none;'
        'font:14px/1.2 system-ui">'
        f'{label}</a>'
    )
    i = html.lower().rfind("</body>")
    return html[:i] + btn + html[i:] if i != -1 else html + btn


# фиксируем выбор EN и возвращаемся на ту же страницу
@app.get("/set-lang/en")
def set_lang_en(request: Request):
    ref = request.headers.get("referer") or "/"
    resp = RedirectResponse(url=ref, status_code=303)
    resp.set_cookie("lang", "en", httponly=True, samesite="lax")
    return resp


@app.get("/set-lang/ru")
def set_lang_ru(request: Request):
    ref = request.headers.get("referer") or "/"
    resp = RedirectResponse(url=ref, status_code=303)
    resp.set_cookie("lang", "ru", httponly=True, samesite="lax")
    return resp


def render_i18n(template_name: str, request: Request, page_key: str, ctx: dict) -> HTMLResponse:
    # всегда добавляем {"request": request}
    ctx = {**ctx, "request": request}
    rendered = templates.get_template(template_name).render(ctx)
    lang = request.cookies.get("lang") or tr.detect_browser_lang(request.headers.get("accept-language", "")) or "ru"
    translated = tr.translate_html(rendered, target_lang=lang, page_name=page_key)
    return HTMLResponse(content=_inject_en_button(translated, lang))


# универсальный роут для всех HTML-страниц

@app.get("/api/resource/{rid}")
async def api_resource_get(
        rid: str,
        request: Request,
        db: SASession = Depends(get_db),
):
    # проверка UUID
    try:
        rid_uuid = UUID(rid)
    except ValueError:
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    row = db.execute(select(Resource).where(Resource.id == rid_uuid)).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    # доступ: владелец или админ
    role_val = user.role.value if hasattr(user.role, "value") else str(user.role)
    if role_val != "admin" and row.user_id != user.id:
        raise HTTPException(status_code=403, detail="FORBIDDEN")

    return {
        "ok": True,
        "id": str(row.id),
        "provider": row.provider,
        "label": row.label,
        "meta_json": row.meta_json or {},
        "status": row.status,
        "phase": row.phase,
        "last_error_code": row.last_error_code,
    }


# ────────────────────────────────────────────────────────────────────────────────
# RESOURCE (новая модель): список + включение/пауза с валидацией meta_json
# ────────────────────────────────────────────────────────────────────────────────
@app.put("/api/resource/{rid}")
async def api_resources_update(
        rid: str,
        payload: dict,
        request: Request,
        db: SASession = Depends(get_db),
):
    # валидируем UUID, чтобы не ловить /api/resources/list как rid
    try:
        rid_uuid = UUID(rid)
    except ValueError:
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    row = db.execute(select(Resource).where(Resource.id == rid_uuid)).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    role_val = user.role.value if hasattr(user.role, "value") else str(user.role)
    if role_val != "admin" and row.user_id != user.id:
        raise HTTPException(status_code=403, detail="FORBIDDEN")

    # что обновляем
    new_label = (payload.get("label") or "").strip() if "label" in payload else row.label
    if "meta_json" in payload:
        new_meta = payload.get("meta_json")
        if not isinstance(new_meta, dict):
            return JSONResponse({"ok": False, "error": "META_FORMAT"}, status_code=400)
        ok, issues = validate_provider_meta(row.provider, new_meta or {})
        if not ok:
            return JSONResponse({"ok": False, "error": "META_INVALID", "issues": issues}, status_code=400)
        row.meta_json = new_meta

    row.label = new_label or row.label

    db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "ok": True,
        "id": str(row.id),
        "provider": row.provider,
        "label": row.label,
        "meta_json": row.meta_json or {},
        "status": row.status,
        "phase": row.phase,
    }


@app.get("/api/resources/list")
async def api_resources_list(request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    q = select(Resource).where(Resource.user_id == user.id)
    created_at_col = getattr(Resource, "created_at", None)
    if created_at_col is not None:
        q = q.order_by(created_at_col.desc())
    rows = db.execute(q).scalars().all()

    items = []
    for r in rows:
        meta = r.meta_json or {}
        ok, issues = validate_provider_meta(r.provider, meta)
        items.append({
            "id": str(r.id),
            "provider": r.provider,
            "label": r.label,
            "status": r.status,
            "phase": r.phase,
            "last_error_code": getattr(r, "last_error_code", None),  # было: r.last_error_code
            "valid": ok,
            "issues": issues,
        })
    return {"ok": True, "items": items}


@app.post("/api/resources/toggle")
async def api_resources_toggle(payload: dict, request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    rid = (payload.get("id") or "").strip()
    action = (payload.get("action") or "").strip()  # 'activate' | 'pause'
    if not rid or action not in {"activate", "pause"}:
        return JSONResponse({"ok": False, "error": "VALIDATION"}, status_code=400)

    # грузим ресурс
    row = db.execute(select(Resource).where(Resource.id == rid)).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    # доступ: владелец или админ
    role_val = row_user_role = user.role.value if hasattr(user.role, "value") else str(user.role)
    if role_val != "admin" and row.user_id != user.id:
        raise HTTPException(status_code=403, detail="FORBIDDEN")

    # если включаем — проверим meta_json по правилам провайдера
    if action == "activate":
        ok, issues = validate_provider_meta(row.provider, row.meta_json or {})
        if not ok:
            return JSONResponse(
                {"ok": False, "error": "META_INVALID", "issues": issues},
                status_code=400,
            )
        row.status = "active"
        # менеджер переведёт фазу дальше; здесь держим ready
        if row.phase in (None, "paused", "error"):
            row.phase = "ready"
    else:
        row.status = "paused"
        row.phase = "paused"

    db.add(row)
    db.commit()
    return {"ok": True, "status": row.status, "phase": row.phase}


@app.post("/api/resources/add")
async def api_resources_add(payload: dict, request: Request, db: SASession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)

    provider = (payload.get("provider") or "").strip()
    label = (payload.get("label") or "").strip() or provider
    meta = payload.get("meta_json")

    if provider not in PROVIDERS:
        return JSONResponse({"ok": False, "error": "UNKNOWN_PROVIDER"}, status_code=400)

    # если meta не передан → берем дефолт
    if not isinstance(meta, dict):
        meta = PROVIDERS[provider]["template"]

    new_res = Resource(
        user_id=user.id,
        provider=provider,
        label=label,
        status="paused",
        phase="draft",
        meta_json=meta,
        created_at=datetime.now(timezone.utc),
    )
    db.add(new_res)
    db.commit()
    db.refresh(new_res)

    return {
        "ok": True,
        "id": str(new_res.id),
        "provider": new_res.provider,
        "label": new_res.label,
        "status": new_res.status,
        "phase": new_res.phase,
    }



@app.post("/api/resource/{rid}/activate")
async def api_resource_activate(
    rid: str,
    request: Request,
    payload: dict = Body(...),
    db: SASession = Depends(get_db),
):
    """
    Шаг 1 (без code): send_code_request — держим живой client в памяти, сохраняем pending_session в БД.
    Шаг 2 (с code): если клиент ещё жив — sign_in только с code (использует sent_code из памяти).
                    если клиент потерян — fallback: sign_in(phone, code, phone_code_hash).
    """
    from uuid import UUID
    from telethon.errors import FloodWaitError, PhoneCodeInvalidError, PhoneNumberInvalidError

    print(f"\n[TG_ACT][{rid}] activate called. Payload keys={list(payload.keys())}")

    # --- доступ/ресурс ---
    try:
        rid_uuid = UUID(rid)
    except ValueError:
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    user = get_current_user(request, db)
    if not user:
        print(f"[TG_ACT][{rid}] UNAUTHORIZED")
        return JSONResponse({"ok": False, "error": "UNAUTHORIZED"}, status_code=401)

    row: Resource | None = db.execute(
        select(Resource).where(Resource.id == rid_uuid)
    ).scalar_one_or_none()
    if not row:
        print(f"[TG_ACT][{rid}] NOT_FOUND")
        raise HTTPException(status_code=404, detail="NOT_FOUND")

    if row.provider != "telegram":
        print(f"[TG_ACT][{rid}] NOT_TELEGRAM")
        return {"ok": False, "error": "NOT_TELEGRAM"}

    # --- данные ---
    meta = row.meta_json or {}
    creds = dict(meta.get("creds") or {})

    phone = (
        payload.get("phone")
        or payload.get("phone_e164")
        or creds.get("phone_e164")
        or creds.get("phone")
    )
    app_id = (
        payload.get("app_id")
        or payload.get("api_id")
        or creds.get("app_id")
        or creds.get("api_id")
    )
    app_hash = (
        payload.get("app_hash")
        or payload.get("api_hash")
        or creds.get("app_hash")
        or creds.get("api_hash")
    )
    code = (payload.get("code") or "").strip() or None

    try:
        app_id = int(app_id) if app_id is not None else None
    except Exception:
        app_id = None

    print(f"[TG_ACT][{rid}] extracted phone={phone} app_id={app_id} app_hash={'SET' if app_hash else 'NONE'} code={'SET' if code else 'NONE'}")

    if not phone or not app_id or not app_hash:
        print(f"[TG_ACT][{rid}] MISSING_FIELDS")
        return {"ok": False, "error": "MISSING_FIELDS"}

    # уже активен?
    if (creds.get("string_session") or "").strip():
        print(f"[TG_ACT][{rid}] already active → status=active/ready")
        row.status = "active"
        row.phase = "ready"
        row.last_error_code = None
        db.commit()
        return {"ok": True, "activated": True}

    # ─────────── ШАГ 1: отправить код (без code) ───────────
    if not code:
        # flood guard
        now = int(time.time())
        flood_until = int(creds.get("flood_until_ts") or 0)
        if flood_until and flood_until > now:
            wait_left = flood_until - now
            print(f"[TG_ACT][{rid}] FLOOD_WAIT active: {wait_left}s left")
            return {"ok": False, "error": "FLOOD_WAIT", "wait_seconds": wait_left}

        # зачистим прошлые подвисшие клиенты
        old = PENDING_TG.get(rid)
        if old:
            try:
                print(f"[TG_ACT][{rid}] found old pending → disconnect+drop")
                await old["client"].disconnect()
            except Exception as e:
                print(f"[TG_ACT][{rid}] old pending disconnect error:", repr(e))
            finally:
                PENDING_TG.pop(rid, None)

        client = TelegramClient(StringSession(), app_id, app_hash)
        await client.connect()
        print(f"[TG_ACT][{rid}] client CONNECTED (step1). session_len={len(client.session.save())}")

        try:
            result = await client.send_code_request(phone)
            print(f"[TG_ACT][{rid}] send_code_request OK. phone_code_hash={getattr(result, 'phone_code_hash', None)}")
        except FloodWaitError as e:
            wait_sec = getattr(e, "seconds", None) or int(str(e).split()[3])
            creds["flood_until_ts"] = int(time.time()) + int(wait_sec)
            meta["creds"] = creds
            row.meta_json = meta
            row.phase = "error"
            row.last_error_code = "FLOOD_WAIT"
            db.commit()
            print(f"[TG_ACT][{rid}] FLOOD_WAIT: {wait_sec}s; saved flood_until_ts")
            await client.disconnect()
            return {"ok": False, "error": "FLOOD_WAIT", "wait_seconds": int(wait_sec)}
        except PhoneNumberInvalidError:
            print(f"[TG_ACT][{rid}] PHONE_INVALID")
            await client.disconnect()
            return {"ok": False, "error": "PHONE_INVALID"}
        except Exception as e:
            print(f"[TG_ACT][{rid}] send_code_request ERROR: {type(e).__name__} {repr(e)}")
            traceback.print_exc()
            await client.disconnect()
            return {"ok": False, "error": str(e)}

        # сохраняем хэши и pending_session
        creds["phone_e164"] = phone
        creds["phone_code_hash"] = result.phone_code_hash
        pending_session = client.session.save()
        creds["pending_session"] = pending_session
        creds.pop("flood_until_ts", None)

        meta["creds"] = creds
        row.meta_json = meta
        row.phase = "waiting_code"
        row.last_error_code = None
        db.commit()

        # держим клиент живым в памяти
        PENDING_TG[rid] = {
            "client": client,
            "session": pending_session,
            "phone": phone,
            "app_id": app_id,
            "app_hash": app_hash,
            "sent_code": result,   # 🔵 сохраняем сам объект sent_code
            "ts": time.time(),
        }
        print(f"[TG_ACT][{rid}] step1 OK → waiting code. pending_session_len={len(pending_session)}; PENDING_TG set")

        return {"ok": True, "need_code": True}

    # ─────────── ШАГ 2: подтверждение кода ───────────
    db.refresh(row)
    creds = dict((row.meta_json or {}).get("creds") or {})
    phone_code_hash = creds.get("phone_code_hash")
    pending_session = creds.get("pending_session")
    if not phone_code_hash:
        print(f"[TG_ACT][{rid}] MISSING_PHONE_CODE_HASH")
        return {"ok": False, "error": "MISSING_PHONE_CODE_HASH"}

    entry = PENDING_TG.get(rid)
    use_fallback = False
    if entry and (time.time() - entry.get("ts", 0) <= PENDING_TG_TTL):
        client = entry["client"]
        print(f"[TG_ACT][{rid}] step2: reuse alive client from memory")
        try:
            await client.sign_in(code=code)   # 🔵 используем короткий вариант
            print(f"[TG_ACT][{rid}] sign_in SUCCESS (with sent_code)")
            final_session = client.session.save()
        except PhoneCodeInvalidError:
            print(f"[TG_ACT][{rid}] CODE_INVALID (with sent_code)")
            return {"ok": False, "error": "CODE_INVALID"}
        except Exception as e:
            print(f"[TG_ACT][{rid}] sign_in ERROR (with sent_code): {repr(e)}")
            traceback.print_exc()
            return {"ok": False, "error": str(e)}
    else:
        # fallback (сервер перезапускался, sent_code потерян)
        if not pending_session:
            print(f"[TG_ACT][{rid}] MISSING_PENDING_SESSION")
            return {"ok": False, "error": "MISSING_PENDING_SESSION"}
        client = TelegramClient(StringSession(pending_session), app_id, app_hash)
        await client.connect()
        use_fallback = True
        print(f"[TG_ACT][{rid}] step2: fallback client CONNECTED from pending_session")
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
            print(f"[TG_ACT][{rid}] sign_in SUCCESS (fallback)")
            final_session = client.session.save()
        except PhoneCodeInvalidError:
            print(f"[TG_ACT][{rid}] CODE_INVALID (fallback)")
            return {"ok": False, "error": "CODE_INVALID"}
        except Exception as e:
            print(f"[TG_ACT][{rid}] sign_in ERROR (fallback): {repr(e)}")
            traceback.print_exc()
            return {"ok": False, "error": str(e)}

    # финал
    creds["string_session"] = final_session
    creds.pop("phone_code_hash", None)
    creds.pop("pending_session", None)
    meta["creds"] = creds
    row.meta_json = meta
    row.status = "active"
    row.phase = "ready"
    row.last_error_code = None
    db.commit()
    print(f"[TG_ACT][{rid}] FINAL: activated. string_session_len={len(final_session)} fallback={use_fallback}")

    try:
        await client.disconnect()
        print(f"[TG_ACT][{rid}] client DISCONNECTED after activation")
    finally:
        PENDING_TG.pop(rid, None)

    return {"ok": True, "activated": True}


@app.get("/{full_path:path}", response_class=HTMLResponse)
def render_any_html(request: Request, full_path: str = ""):
    # URL → шаблон:
    #   /               -> index.html
    #   /auth/login     -> auth/login.html
    #   /docs/          -> docs/index.html
    path = full_path.strip("/")
    if path == "" or path.endswith("/"):
        path = path + "index"
    if not path.endswith(".html"):
        path = path + ".html"
    if ".." in path or path.startswith("/"):
        return HTMLResponse("Not found", status_code=404)

    try:
        rendered = templates.get_template(path).render(request=request)
    except Exception:
        return HTMLResponse("Not found", status_code=404)

    lang = _get_lang(request)
    page_key = path[:-5].replace("/", "_")  # для раздельного кэша
    translated = tr.translate_html(rendered, target_lang=lang, page_name=page_key)
    return HTMLResponse(content=_inject_en_button(translated, lang))
