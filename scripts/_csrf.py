"""CSRF / cross-origin protection for the local dashboard.

The Command Centre serves an *unauthenticated* API bound to localhost.
Without an Origin check, any web page the user happens to have open can
issue cross-origin ``POST`` / ``DELETE`` / ... requests to
``http://127.0.0.1:<port>/...`` and trigger side effects (emergency-stop,
task creation, dispatcher runs, schedule deletion).

CORS does **not** prevent this — it only governs whether the *response* is
readable by script, not whether the request reaches the handler. The side
effect happens regardless. The classic defense for an unauthenticated
local service is to check the ``Origin`` header on state-changing methods.

Policy:

* No ``Origin`` header  -> non-browser client (the OTEL exporter Claude
  Code uses, ``curl``, server-to-server). Not a CSRF vector. **Allow.**
* ``Origin`` on a localhost host -> the dashboard's own UI (served
  same-origin, or the Vite dev server). **Allow.**
* Any other ``Origin`` -> a foreign web page driving the user's browser.
  **Block** with 403.

This is port-agnostic: the server only binds localhost, so every
legitimate browser request carries a localhost Origin. DNS-rebinding does
not help an attacker here — it forges the ``Host`` header, not ``Origin``.
"""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import JSONResponse

# Methods that cannot change server state are never guarded.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

# Hostnames that count as "the dashboard itself" (it only binds localhost).
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})


def origin_is_local(origin: str) -> bool:
    """True if ``origin`` (an ``Origin`` header value) names a localhost host."""
    try:
        host = urlparse(origin).hostname
    except ValueError:
        return False
    return host in LOCAL_HOSTS


def origin_allowed(origin: str | None) -> bool:
    """Decide whether a state-changing request may proceed.

    Returns ``True`` for missing Origin (non-browser client) or a localhost
    Origin (the dashboard's own UI); ``False`` for any foreign Origin.
    """
    if not origin:
        return True
    return origin_is_local(origin)


async def csrf_origin_guard(request: Request, call_next):
    """ASGI middleware: block cross-origin state-changing requests."""
    if request.method not in SAFE_METHODS:
        if not origin_allowed(request.headers.get("origin")):
            return JSONResponse(
                {"detail": "Cross-origin request blocked (CSRF protection)"},
                status_code=403,
            )
    return await call_next(request)
