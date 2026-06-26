# src/app/web_routes.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session as SASession

from src.app.core.auth import get_current_user, require_admin
from src.app.core.db import engine, get_db
from src.app.core.templates import build_page_context, render_i18n
from src.models.user import User

router = APIRouter()


def _require_user(request: Request, db: SASession):
    user = get_current_user(request, db)
    if not user:
        return None
    return user


@router.get("/", response_class=HTMLResponse)
async def index_page(request: Request, db: SASession = Depends(get_db)):
    return render_i18n("index.html", request, "index", build_page_context(request, db))


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, db: SASession = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)
    return render_i18n("profile.html", request, "profile", build_page_context(request, db))


@router.get("/resources", response_class=HTMLResponse)
async def resources_page(request: Request, db: SASession = Depends(get_db)):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)
    return render_i18n("resources.html", request, "resources", build_page_context(request, db))


@router.get("/resources/{provider}/{rid}", response_class=HTMLResponse)
async def resource_universal_page(
    provider: str, rid: str, request: Request, db: SASession = Depends(get_db)
):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    return render_i18n(
        f"resources/{provider}.html",
        request,
        f"resource_{provider}",
        build_page_context(request, db, rid=rid),
    )


@router.get("/ai", response_class=HTMLResponse)
async def ai_page(request: Request, db: SASession = Depends(get_db)):
    return render_i18n("ai.html", request, "ai", build_page_context(request, db))


@router.get("/callcenter", response_class=HTMLResponse)
async def callcenter_page(request: Request, db: SASession = Depends(get_db)):
    return render_i18n("callcenter.html", request, "callcenter", build_page_context(request, db))


@router.get("/tables", response_class=HTMLResponse)
async def tables(request: Request, db: SASession = Depends(get_db), _: User = Depends(require_admin)):
    user = _require_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    data = {}
    with engine.connect() as conn:
        for table in table_names:
            cols = [col["name"] for col in inspector.get_columns(table)]
            rows = conn.execute(text(f'SELECT * FROM "{table}"')).fetchall()
            data[table] = {"columns": cols, "rows": rows}

    return render_i18n(
        "all-tables.html",
        request,
        "tables_index",
        build_page_context(request, db, data=data),
    )
