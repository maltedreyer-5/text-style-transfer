# SPDX-FileCopyrightText: 2026 Malte Dreyer
# SPDX-License-Identifier: MIT
"""Response headers and authentication behind a reverse proxy.

Hiding an event from the API documentation does not protect it: the browser
must be able to call every event, and so can any script. For this reason no
event performs a privileged operation; every event only reads packaged data
and works on the caller's own session.
"""

from __future__ import annotations

from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware

from ..config import Config

# A full Content-Security-Policy is not set because Gradio relies on inline
# scripts and styles; frame-ancestors alone prevents embedding (clickjacking).
HEADERS = {
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


class SecurityHeaders(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        for name, value in HEADERS.items():
            response.headers.setdefault(name, value)
        return response


def middleware(config: Config) -> list[Middleware]:
    return [Middleware(SecurityHeaders)] if config.security_headers else []


def auth_dependency(config: Config):  # type: ignore[no-untyped-def]
    """Return the user id the proxy put into the configured header.

    The proxy must remove this header from incoming requests; otherwise any
    client can claim any identity.
    """
    if not config.auth_header:
        return None
    header = config.auth_header

    def dependency(request) -> str | None:  # type: ignore[no-untyped-def]
        value = (request.headers.get(header) or "").strip()
        return value or None

    return dependency
