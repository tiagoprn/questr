from __future__ import annotations

import hashlib
import hmac
from uuid import UUID

from fastapi.responses import JSONResponse
from starlette.middleware.base import (
    BaseHTTPMiddleware,
    RequestResponseEndpoint,
)
from starlette.requests import Request
from starlette.responses import Response

from questr.domains.users.repository import SessionRepository
from questr.infrastructure.orm.base import AsyncSessionLocal


class CsrfMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that enforces CSRF for state-changing requests.

    Safe methods (GET, HEAD, OPTIONS) and pre-auth allowlisted routes
    (``/api/v1/auth/login``, ``/signup``, ``/resend-verification``) pass
    through unchallenged.

    For other state-changing requests the middleware enforces:
    1. Session-validity-first: an invalid/expired session passes through
       to the auth dependency (which returns 401).
    2. Double-submit: the ``X-CSRF-Token`` header must match the
       ``csrf_token`` cookie (``hmac.compare_digest``).
    3. Synchronizer token: the SHA-256 hash of the header value must
       match the server-stored ``csrf_token_hash``.

    Rejections are returned as direct ``JSONResponse`` (not exceptions)
    because Starlette's exception handlers are inside the middleware
    layer and cannot catch exceptions raised from middleware.
    """

    SAFE_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS'})

    EXEMPT_PATHS = frozenset({
        '/api/v1/auth/login',
        '/api/v1/auth/signup',
        '/api/v1/auth/resend-verification',
    })

    async def dispatch(  # noqa: PLR0911
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        # Safe methods always pass through
        if request.method in self.SAFE_METHODS:
            return await call_next(request)

        # Pre-auth allowlisted routes pass through
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        # No session cookie -> no CSRF check; auth dependency handles it
        session_id = request.cookies.get('session_id')
        if session_id is None:
            return await call_next(request)

        # Malformed session cookie -> let auth dependency return 401
        try:
            session_uuid = UUID(session_id)
        except ValueError:
            return await call_next(request)

        # Session-validity-first: a stale/inactive session passes through
        # so the auth dependency (not the middleware) decides the response
        async with AsyncSessionLocal() as db:
            session_repo = SessionRepository(db)
            session = await session_repo.get_by_id(session_uuid)

        if session is None or not session.is_active:
            return await call_next(request)

        # CSRF enforcement
        csrf_cookie = request.cookies.get('csrf_token')
        csrf_header = request.headers.get('X-CSRF-Token')

        if csrf_header is None or csrf_cookie is None:
            return self._reject('CSRF token missing', 'csrf_token_missing')

        # Double-submit check: header must echo the cookie
        if not hmac.compare_digest(csrf_header, csrf_cookie):
            return self._reject('CSRF token mismatch', 'csrf_token_mismatch')

        # Synchronizer check: hash(header) must match stored hash
        header_hash = hashlib.sha256(csrf_header.encode()).hexdigest()
        if not hmac.compare_digest(header_hash, session.csrf_token_hash):
            return self._reject('CSRF token mismatch', 'csrf_token_mismatch')

        return await call_next(request)

    @staticmethod
    def _reject(detail: str, error_code: str) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={'detail': detail, 'error_code': error_code},
        )
