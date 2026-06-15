import os
from unittest.mock import patch

from starlette.requests import Request

from src.app.core.geo import (
    get_client_ip,
    get_country_code,
    is_google_auth_enabled,
)


def _request(headers: dict[str, str] | None = None, client: str = "127.0.0.1") -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request(
        {
            "type": "http",
            "headers": raw,
            "method": "GET",
            "path": "/",
            "client": (client, 0),
        }
    )


def test_country_from_cloudflare_header():
    req = _request({"CF-IPCountry": "ru"})
    assert get_country_code(req) == "RU"


def test_country_from_custom_header():
    req = _request({"X-Country-Code": "de"})
    assert get_country_code(req) == "DE"


def test_client_ip_from_x_real_ip():
    req = _request({"X-Real-IP": "203.0.113.10"})
    assert get_client_ip(req) == "203.0.113.10"


@patch("src.app.core.geo._country_from_ip", return_value="AZ")
def test_country_from_client_ip(mock_lookup):
    req = _request({"X-Real-IP": "203.0.113.10"})
    assert get_country_code(req) == "AZ"
    mock_lookup.assert_called_once_with("203.0.113.10")


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
def test_google_enabled_when_country_unknown_in_prod():
    assert is_google_auth_enabled(_request()) is True


@patch.dict(os.environ, {"ENV": "prod"}, clear=False)
@patch("src.app.core.geo._country_from_ip", return_value="RU")
def test_google_disabled_for_ru_ip_lookup(_mock):
    req = _request({"X-Real-IP": "95.142.46.1"})
    assert is_google_auth_enabled(req) is False
