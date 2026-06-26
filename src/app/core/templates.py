"""
src/app/core/templates.py — шаблоны Jinja2 и post-render i18n (auto-i18n-lib).
"""

import os

from autoi18n import Translator
from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.app.core.config import (
    TEMPLATES_DIR,
    TRANSLATIONS_DIR,
    get_i18n_lang_labels,
)
from src.app.core.geo import is_google_auth_enabled

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

tr = Translator(
    cache_dir=str(TRANSLATIONS_DIR),
    source_lang=os.getenv("SOURCE_LANG", "ru"),
    target_langs=os.getenv("AUTO_I18N_TARGET_LANGS", "en"),
    api_key=os.getenv("OPENAI_API_KEY", "local-no-key"),
)


def available_langs() -> list[str]:
    langs = [tr.source_lang]
    for lang in tr.target_langs:
        if lang not in langs:
            langs.append(lang)
    return langs


def lang_label(lang: str) -> str:
    labels = get_i18n_lang_labels()
    normalized = (lang or "").lower()
    return labels.get(normalized, normalized.upper() or tr.source_lang.upper())


def _get_lang(request: Request) -> str:
    """Язык: cookie → Accept-Language → source_lang."""
    allowed = set(available_langs())

    cookie = (request.cookies.get("lang") or "").lower()
    if cookie in allowed:
        return cookie

    browser = tr.detect_browser_lang(request.headers.get("accept-language", ""))
    if browser in allowed:
        return browser

    return tr.source_lang


def _inject_lang_switcher(html: str, current_lang: str) -> str:
    """Выпадающий переключатель языков из настроек (SOURCE_LANG + AUTO_I18N_TARGET_LANGS)."""
    if 'id="i18n-switcher"' in html:
        return html

    langs = available_langs()
    if len(langs) <= 1:
        return html

    cur = (current_lang or tr.source_lang).lower()
    items = []
    for lang in langs:
        label = lang_label(lang)
        active = ' class="active"' if lang == cur else ""
        items.append(
            f'<li role="option"{active}>'
            f'<a href="/set-lang/{lang}" data-lang="{lang}">{label}</a>'
            f"</li>"
        )

    switcher = (
        '<div id="i18n-switcher" class="i18n-switcher">'
        f'<button type="button" id="i18n-switcher-btn" '
        f'aria-haspopup="listbox" aria-expanded="false" aria-label="Language">'
        f"{lang_label(cur)}"
        "</button>"
        f'<ul id="i18n-switcher-menu" class="i18n-switcher-menu hidden" role="listbox">'
        + "".join(items)
        + "</ul></div>"
    )

    marker = "</body>"
    idx = html.lower().rfind(marker)
    if idx == -1:
        return html + switcher
    return html[:idx] + switcher + html[idx:]


def render_i18n(template_name: str, request: Request, page_key: str, ctx: dict) -> HTMLResponse:
    """Рендер шаблона + post-render перевод + переключатель языков."""
    lang = _get_lang(request)
    ctx = {
        **ctx,
        "request": request,
        "page_key": page_key,
        "lang": lang,
        "google_auth_enabled": is_google_auth_enabled(request),
    }
    rendered = templates.get_template(template_name).render(ctx)
    translated = tr.translate_html(rendered, target_lang=lang, page_name=page_key)
    return HTMLResponse(content=_inject_lang_switcher(translated, lang))


def set_lang(request: Request, lang: str) -> RedirectResponse:
    """Устанавливает cookie lang и возвращает на referer."""
    normalized = (lang or "").lower()
    if normalized not in available_langs():
        normalized = tr.source_lang

    ref = request.headers.get("referer") or "/"
    resp = RedirectResponse(url=ref, status_code=303)
    resp.set_cookie("lang", normalized, httponly=True, samesite="lax")
    return resp
