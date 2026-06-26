from unittest.mock import patch

from starlette.requests import Request

from src.app.core.templates import (
    _get_lang,
    _inject_lang_switcher,
    available_langs,
    set_lang,
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


def test_available_langs_includes_source_and_targets():
    with patch.object(tr, "source_lang", "ru"), patch.object(tr, "target_langs", ["en", "az"]):
        assert available_langs() == ["ru", "en", "az"]


def test_get_lang_from_cookie():
    req = _request(cookies={"lang": "en"})
    with patch("src.app.core.templates.available_langs", return_value=["ru", "en"]):
        assert _get_lang(req) == "en"


def test_get_lang_falls_back_to_source():
    req = _request(cookies={"lang": "de"})
    with patch("src.app.core.templates.available_langs", return_value=["ru", "en"]):
        assert _get_lang(req) == "ru"


def test_inject_lang_switcher_lists_configured_langs():
    html = "<html><body></body></html>"
    with patch("src.app.core.templates.available_langs", return_value=["ru", "en", "az"]):
        with patch("src.app.core.templates.lang_label", side_effect=lambda code: code.upper()):
            out = _inject_lang_switcher(html, "ru")

    assert 'id="i18n-switcher"' in out
    assert "/set-lang/ru" in out
    assert "/set-lang/en" in out
    assert "/set-lang/az" in out
    assert 'class="active"' in out


def test_set_lang_rejects_unknown_lang():
    req = _request(headers={"referer": "/"})
    with patch("src.app.core.templates.available_langs", return_value=["ru", "en"]):
        resp = set_lang(req, "xx")

    assert resp.status_code == 303
    assert resp.headers["set-cookie"].startswith("lang=ru")
