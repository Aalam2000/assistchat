from unittest.mock import patch

from starlette.requests import Request

from src.app.core.templates import (
    build_page_context,
    get_supported_ui_languages,
    get_ui_lang,
    render_i18n,
    template_to_page_key,
    tr,
)


def _request(
    cookies: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> Request:
    merged = dict(headers or {})
    if cookies:
        merged["cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in merged.items()]
    return Request(
        {
            "type": "http",
            "headers": raw_headers,
            "method": "GET",
            "path": "/",
            "client": ("127.0.0.1", 0),
        }
    )


def test_template_to_page_key():
    assert template_to_page_key("index.html") == "index"
    assert template_to_page_key("resources/telegram.html") == "resource_telegram"


def test_get_ui_lang_from_cookie():
    req = _request(cookies={"ui_lang": "en"})
    with patch("src.app.core.templates.get_supported_ui_languages", return_value=["ru", "en"]):
        assert get_ui_lang(req) == "en"


def test_get_ui_lang_falls_back_to_source():
    req = _request(cookies={"ui_lang": "de"})
    with patch("src.app.core.templates.get_supported_ui_languages", return_value=["ru", "en"]):
        assert get_ui_lang(req) == "ru"


def test_render_i18n_skips_translation_for_source_lang():
    req = _request(cookies={"ui_lang": "ru"})
    ctx = build_page_context(req)
    with patch.object(tr, "translate_html") as translate_mock:
        resp = render_i18n("index.html", req, "index", ctx)
    translate_mock.assert_not_called()
    assert "langSwitch" in resp.body.decode()


def test_render_i18n_translates_non_source_lang():
    req = _request(cookies={"ui_lang": "en"})
    ctx = build_page_context(req)
    with patch.object(tr, "translate_html", return_value="<html>EN</html>") as translate_mock:
        resp = render_i18n("index.html", req, "index", ctx)
    translate_mock.assert_called_once()
    assert resp.body.decode() == "<html>EN</html>"
