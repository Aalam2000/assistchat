"""
Определение страны посетителя: заголовки CDN/nginx → IP → GeoIP.
"""
from __future__ import annotations

import functools
import ipaddress
import os

import requests
from fastapi import Request

_COUNTRY_HEADERS = (
    "CF-IPCountry",
    "X-Country-Code",
    "CloudFront-Viewer-Country",
)

_GEOIP_DB_PATH = os.getenv("GEOIP_DB_PATH", "/app/geoip/GeoLite2-Country.mmdb")
_geoip_reader = None


def _get_geoip_reader():
    global _geoip_reader
    if _geoip_reader is not None:
        return _geoip_reader
    if not os.path.isfile(_GEOIP_DB_PATH):
        return None
    try:
        import geoip2.database

        _geoip_reader = geoip2.database.Reader(_GEOIP_DB_PATH)
    except Exception:
        _geoip_reader = None
    return _geoip_reader


def get_client_ip(request: Request) -> str | None:
    """IP посетителя: X-Forwarded-For → X-Real-IP → socket."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
        if ip:
            return ip

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    if request.client and request.client.host:
        return request.client.host
    return None


def _is_public_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (addr.is_private or addr.is_loopback or addr.is_link_local)


@functools.lru_cache(maxsize=4096)
def _country_from_ip(ip: str) -> str | None:
    """Страна по IP: локальная GeoIP-база, иначе ip-api.com (кэш)."""
    if not _is_public_ip(ip):
        return None

    reader = _get_geoip_reader()
    if reader:
        try:
            return reader.country(ip).country.iso_code
        except Exception:
            pass

    try:
        resp = requests.get(
            f"http://ip-api.com/json/{ip}?fields=status,countryCode",
            timeout=2,
        )
        data = resp.json()
        if data.get("status") == "success":
            code = data.get("countryCode")
            return str(code).upper() if code else None
    except Exception:
        pass
    return None


def get_country_code(request: Request) -> str | None:
    """ISO-код страны (RU, AZ, …) или None."""
    for header in _COUNTRY_HEADERS:
        raw = request.headers.get(header)
        if raw:
            code = raw.strip().upper()
            if code and code != "XX":
                return code

    ip = get_client_ip(request)
    if ip:
        return _country_from_ip(ip)
    return None


def is_google_auth_enabled(request: Request) -> bool:
    """
    Google OAuth скрыт только для RU.
    Dev: всегда доступен.
    """
    if os.getenv("ENV", "dev").lower() == "dev":
        return True

    country = get_country_code(request)
    return country != "RU"
