"""
Определение страны по IP через заголовки CDN / reverse proxy.
"""
from __future__ import annotations

import os

from fastapi import Request

_COUNTRY_HEADERS = (
    "CF-IPCountry",
    "X-Country-Code",
    "CloudFront-Viewer-Country",
)


def get_country_code(request: Request) -> str | None:
    """Возвращает ISO-код страны (RU, US, …) или None, если заголовок не передан."""
    for header in _COUNTRY_HEADERS:
        raw = request.headers.get(header)
        if raw:
            code = raw.strip().upper()
            if code and code != "XX":
                return code
    return None


def is_google_auth_enabled(request: Request) -> bool:
    """
    Google OAuth доступен, если:
    - dev-окружение, или
    - страна определена и это не RU.

    В prod без заголовка страны Google скрыт (fail-closed для проверок с RU IP).
    """
    if os.getenv("ENV", "dev").lower() == "dev":
        return True

    country = get_country_code(request)
    if not country:
        return False
    return country != "RU"
