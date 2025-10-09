"""
core/templates.py — работа с шаблонами Jinja2 и механизмом переводов (i18n).
"""

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from autoi18n import Translator
from src.app.core.config import BASE_DIR

# Инициализация шаблонов и переводчика
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
tr = Translator(cache_dir="./translations")

def _get_lang(request: Request) -> str:
    """
    Определяет язык интерфейса: cookie → заголовок → ru по умолчанию.
    """
    lang = (request.cookies.get("lang") or "").lower()
    if lang in ("ru", "en"):
        return lang
    return tr.detect_browser_lang(request.headers.get("accept-language", "")) or "ru"

def _inject_en_button(html: str, lang: str) -> str:
    """
    Добавляет кнопку переключения языка (RU/EN) в HTML-страницу перед </body>.
    """
    cur = (lang or "ru").lower()
    label, href = ("RU", "/set-lang/ru") if cur.startswith("en") else ("EN", "/set-lang/en")
    if 'id="i18n-toggle"' in html:
        return html
    btn = f'<a id="i18n-toggle" href="{href}">{label}</a>'
    i = html.lower().rfind("</body>")
    return html[:i] + btn + html[i:] if i != -1 else html + btn

def render_i18n(template_name: str, request: Request, page_key: str, ctx: dict) -> HTMLResponse:
    """
    Рендерит HTML-шаблон с автоматическим переводом и вставкой кнопки EN/RU.
    """
    lang_cookie = request.cookies.get("lang")
    lang_header = tr.detect_browser_lang(request.headers.get("accept-language", ""))
    lang = lang_cookie or lang_header or "ru"

    ctx = {**ctx, "request": request, "page_key": page_key}
    rendered = templates.get_template(template_name).render(ctx)
    translated = tr.translate_html(rendered, target_lang=lang, page_name=page_key)
    return HTMLResponse(content=_inject_en_button(translated, lang))

def set_lang_en(request: Request):
    """
    Меняет язык интерфейса на английский и возвращает RedirectResponse на предыдущую страницу.
    """
    ref = request.headers.get("referer") or "/"
    resp = RedirectResponse(url=ref, status_code=303)
    resp.set_cookie("lang", "en", httponly=True, samesite="lax")
    return resp

def set_lang_ru(request: Request):
    """
    Меняет язык интерфейса на русский и возвращает RedirectResponse на предыдущую страницу.
    """
    ref = request.headers.get("referer") or "/"
    resp = RedirectResponse(url=ref, status_code=303)
    resp.set_cookie("lang", "ru", httponly=True, samesite="lax")
    return resp
