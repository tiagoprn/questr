from __future__ import annotations

import hashlib
import hmac
from uuid import UUID

from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from questr.domains.users.repository import SessionRepository
from questr.infrastructure.orm.base import AsyncSessionLocal


class CsrfMiddleware:
    """ASGI middleware enforcing CSRF for state-changing requests.

    Safe methods (GET, HEAD, OPTIONS) and pre-auth allowlisted routes
    (``/api/v1/auth/login``, ``/signup``, ``/resend-verification``)
    pass through unchallenged.

    For other state-changing requests the middleware enforces:
    1. Session-validity-first: an invalid/expired session passes
       through to the auth dependency (which returns 401).
    2. Double-submit: the ``X-CSRF-Token`` header must match the
       ``csrf_token`` cookie (``hmac.compare_digest``).
    3. Synchronizer token: the SHA-256 hash of the header value
       must match the server-stored ``csrf_token_hash``.

    Uses pure ASGI interface to avoid BaseHTTPMiddleware's
    background-task lifetime issues.
    """

    SAFE_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS'})

    EXEMPT_PATHS = frozenset({
        '/api/v1/auth/login',
        '/api/v1/auth/signup',
        '/api/v1/auth/resend-verification',
    })

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(  # noqa: PLR0911
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        method = scope.get('method', 'GET')
        path = scope.get('path', '')

        if method in self.SAFE_METHODS or path in self.EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        cookies = self._parse_cookies(scope)
        session_id = cookies.get('session_id')

        if session_id is None:
            await self.app(scope, receive, send)
            return

        try:
            session_uuid = UUID(session_id)
        except ValueError:
            await self.app(scope, receive, send)
            return

        # Session-validity-first lookup
        async with AsyncSessionLocal() as db:
            session = await SessionRepository(db).get_by_id(session_uuid)

        if session is None or not session.is_active:
            await self.app(scope, receive, send)
            return

        # CSRF enforcement
        csrf_cookie = cookies.get('csrf_token')
        csrf_header = self._get_header(scope, 'x-csrf-token')

        if csrf_header is None or csrf_cookie is None:
            resp = JSONResponse(
                status_code=403,
                content={
                    'detail': 'CSRF token missing',
                    'error_code': 'csrf_token_missing',
                },
            )
            await resp(scope, receive, send)
            return

        if not hmac.compare_digest(csrf_header, csrf_cookie):
            resp = JSONResponse(
                status_code=403,
                content={
                    'detail': 'CSRF token mismatch',
                    'error_code': 'csrf_token_mismatch',
                },
            )
            await resp(scope, receive, send)
            return

        header_hash = hashlib.sha256(csrf_header.encode()).hexdigest()
        if not hmac.compare_digest(header_hash, session.csrf_token_hash):
            resp = JSONResponse(
                status_code=403,
                content={
                    'detail': 'CSRF token mismatch',
                    'error_code': 'csrf_token_mismatch',
                },
            )
            await resp(scope, receive, send)
            return

        await self.app(scope, receive, send)

    @staticmethod
    def _parse_cookies(scope: Scope) -> dict[str, str]:
        """Parse Cookie header from ASGI scope into a dict."""
        headers = dict(scope.get('headers', []))
        raw = headers.get(b'cookie', b'').decode('latin-1', errors='replace')
        cookies = {}
        for raw_pair in raw.split(';'):
            stripped = raw_pair.strip()
            if '=' in stripped:
                key, val = stripped.split('=', 1)
                cookies[key.strip()] = val.strip()
        return cookies

    @staticmethod
    def _get_header(scope: Scope, name: str) -> str | None:
        """Get a header value from ASGI scope by lowercase name."""
        headers = dict(scope.get('headers', []))
        val = headers.get(name.encode('latin-1'))
        if val is not None:
            return val.decode('latin-1', errors='replace')
        return None
