"""
core/middleware.py — системные промежуточные обработчики (middleware).
Содержит middleware для трассировки авторизации.
"""

from fastapi import Request

async def _authflow_trace(request: Request, call_next):
    """
    Логирует запросы и ответы, связанные с авторизацией и профилем.
    Помогает отлаживать поток логина/сессии.
    """
    path = request.url.path
    watch = path.startswith(("/auth", "/profile", "/api/auth"))
    if watch:
        try:
            sess_keys = list(getattr(request, "session", {}).keys())
        except Exception:
            sess_keys = []
        print(
            "[IN]", request.method, path,
            "host=", request.headers.get("host"),
            "xfp=", request.headers.get("x-forwarded-proto"),
            "cookie=", request.headers.get("cookie"),
            "sess_keys=", sess_keys,
        )
    resp = await call_next(request)
    if watch:
        sc = resp.headers.get("set-cookie", "")
        print(
            "[OUT]", request.method, path,
            "status=", resp.status_code,
            "location=", resp.headers.get("location"),
            "set-cookie(session)=", ("assistchat_session" in sc),
        )
    return resp
