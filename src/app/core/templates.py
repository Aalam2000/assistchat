"""
src/app/core/templates.py — шаблоны Jinja2 и post-render i18n (auto-i18n-lib).
Схема как в cargodb: render → ru as-is, иначе translate_html.
"""

import json
import os

from autoi18n import Translator
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.app.core.config import (
    AUTO_I18N_TARGET_LANGS,
    SOURCE_LANG,
    TEMPLATES_DIR,
    TRANSLATIONS_DIR,
)
from src.app.core.geo import is_google_auth_enabled

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["tojson"] = lambda value: json.dumps(value, ensure_ascii=False)

tr = Translator(
    cache_dir=str(TRANSLATIONS_DIR),
    source_lang=SOURCE_LANG,
    api_key=os.getenv("OPENAI_API_KEY", "local-no-key"),
)


def template_to_page_key(template_name: str) -> str:
    """Имя страницы для кэша переводов (совместимо с существующими *.en.json)."""
    if template_name.startswith("resources/"):
        provider = template_name.split("/")[1].replace(".html", "")
        return f"resource_{provider}"
    return template_name.replace(".html", "").replace("/", "_")


def get_supported_ui_languages() -> list[str]:
    langs = [tr.source_lang]
    for code in AUTO_I18N_TARGET_LANGS:
        normalized = str(code).strip().lower()
        if normalized and normalized not in langs:
            langs.append(normalized)
    return langs


def get_ui_lang(request: Request) -> str:
    lang = (
        request.cookies.get("ui_lang")
        or request.cookies.get("lang")  # legacy cookie
        or ""
    ).strip().lower()
    supported = set(get_supported_ui_languages())
    if lang in supported:
        return lang
    return tr.source_lang


def build_page_context(request: Request, db=None, **extra) -> dict:
    user = extra.pop("user", None)
    if user is None and db is not None:
        from src.app.core.auth import get_current_user

        user = get_current_user(request, db)

    role = None
    if user is not None:
        raw_role = getattr(user, "role", None)
        role = raw_role.value if hasattr(raw_role, "value") else str(raw_role)

    ui_lang = get_ui_lang(request)
    ctx = {
        "user": user,
        "username": user.username if user else extra.get("username"),
        "role": role if user else extra.get("role"),
        "app_languages": get_supported_ui_languages(),
        "current_ui_lang": ui_lang,
        "lang": ui_lang,
    }
    ctx.update(extra)
    return ctx


def render_i18n(
    template_name: str,
    request: Request,
    page_key: str,
    ctx: dict,
    status: int = 200,
) -> HTMLResponse:
    merged = {
        **ctx,
        "request": request,
        "page_key": page_key,
        "google_auth_enabled": is_google_auth_enabled(request),
    }
    if "app_languages" not in merged:
        merged["app_languages"] = get_supported_ui_languages()
    if "current_ui_lang" not in merged:
        merged["current_ui_lang"] = get_ui_lang(request)
    if "lang" not in merged:
        merged["lang"] = merged["current_ui_lang"]

    html = templates.get_template(template_name).render(merged)
    target_lang = merged["current_ui_lang"]

    if target_lang == tr.source_lang:
        return HTMLResponse(content=html, status_code=status)

    try:
        translated = tr.translate_html(
            html=html,
            target_lang=target_lang,
            page_name=page_key,
        )
        return HTMLResponse(content=translated, status_code=status)
    except Exception:
        return HTMLResponse(content=html, status_code=status)
