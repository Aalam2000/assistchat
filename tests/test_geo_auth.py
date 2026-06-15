import os
from unittest.mock import patch

import pytest
from starlette.requests import Request

from src.app.core.geo import get_country_code, is_google_auth_enabled


def _request(headers: dict[str, str] | None = None) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "headers": raw, "method": "GET", "path": "/"})


def test_country_from_cloudflare_header():
    req = _request({"CF-IPCountry": "ru"})
    assert get_country_code(req) == "RU"


def test_country_from_custom_header():
    req = _request({"X-Country-Code": "de"})
    assert get_country_code(req) == "DE"


def test_country_missing():
    assert get_country_code(_request()) is None


@patch.dict(os.environ, {"ENV": "dev"}, clear=False)
def test_google_enabled_in_dev_even_for_ru():
    req = _request({"CF-IPCountry": "RU"})
    assert is_google_auth_enabled(req) is True


@patch.dict(os.environ, {"ENV": "prod"}, clear=False)
def test_google_disabled_for_ru_in_prod():
    req = _request({"CF-IPCountry": "RU"})
    assert is_google_auth_enabled(req) is False


@patch.dict(os.environ, {"ENV": "prod"}, clear=False)
def test_google_enabled_for_non_ru_in_prod():
    req = _request({"CF-IPCountry": "AZ"})
    assert is_google_auth_enabled(req) is True


@patch.dict(os.environ, {"ENV": "prod"}, clear=False)
def test_google_disabled_when_country_unknown_in_prod():
    assert is_google_auth_enabled(_request()) is False
