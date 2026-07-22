# ruff: noqa: PLR2004, PLR6201
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid7

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from questr.app import middleware as mw
from questr.domains.users.repository import Session as SessionDomain
from questr.domains.users.repository import SessionRepository


@pytest.fixture
def test_app() -> FastAPI:
    """Minimal app with CsrfMiddleware and a protected test route."""
    app = FastAPI()
    app.add_middleware(mw.CsrfMiddleware)

    @app.api_route('/protected', methods=['GET', 'POST', 'HEAD', 'OPTIONS'])
    async def protected() -> dict:
        return {'status': 'ok'}

    @app.post('/api/v1/auth/login')
    async def login() -> dict:
        return {'status': 'login'}

    @app.get('/safe')
    async def safe() -> dict:
        return {'status': 'safe'}

    return app


def _make_session(**kwargs: object) -> SessionDomain:
    """Helper to create a SessionDomain with sensible defaults."""
    now = datetime.now(timezone.utc)
    fields = {
        'id': uuid7(),
        'user_id': uuid7(),
        'is_active': True,
        'issued_at': now,
        'last_activity': now,
        'expires_at': now + timedelta(minutes=30),
        'absolute_expires_at': now + timedelta(hours=8),
        'ip_address': '127.0.0.1',
        'user_agent': 'pytest',
        'csrf_token_hash': 'a' * 64,
    }
    fields.update(kwargs)
    return SessionDomain(**fields)


def _patch_session(mock_session: SessionDomain) -> tuple[patch, patch]:
    """Patch SessionRepository.get_by_id and AsyncSessionLocal.

    Returns a tuple of context managers that make the middleware's
    DB session return the given ``mock_session``.
    """
    mock_db = MagicMock()
    mock_db.__aenter__.return_value = mock_db

    repo_patch = patch.object(
        SessionRepository,
        'get_by_id',
        new=AsyncMock(return_value=mock_session),
    )
    db_patch = patch.object(mw, 'AsyncSessionLocal', return_value=mock_db)
    return repo_patch, db_patch


class TestCsrfMiddleware:
    """Tests for CsrfMiddleware."""

    async def test_safe_methods_pass_through(
        self,
        test_app: FastAPI,
    ) -> None:
        """AC-1: Safe methods (GET, HEAD, OPTIONS) pass through."""
        transport = ASGITransport(app=test_app)
        async with AsyncClient(
            transport=transport, base_url='http://test'
        ) as ac:
            for method in ('GET', 'HEAD', 'OPTIONS'):
                resp = await ac.request(method, '/protected')
                assert resp.status_code in (200, 204)

    async def test_exempt_preauth_routes_pass_through(
        self,
        test_app: FastAPI,
    ) -> None:
        """AC-1: Pre-auth allowlisted routes pass through."""
        session = _make_session()
        transport = ASGITransport(app=test_app)
        async with AsyncClient(
            transport=transport, base_url='http://test'
        ) as ac:
            ac.cookies['session_id'] = str(session.id)
            resp = await ac.post('/api/v1/auth/login')
            assert resp.status_code == 200

    async def test_missing_session_cookie_passes_through(
        self,
        test_app: FastAPI,
    ) -> None:
        """AC-2: Missing session cookie passes through."""
        transport = ASGITransport(app=test_app)
        async with AsyncClient(
            transport=transport, base_url='http://test'
        ) as ac:
            resp = await ac.post('/protected')
            assert resp.status_code == 200

    async def test_malformed_session_cookie_passes_through(
        self,
        test_app: FastAPI,
    ) -> None:
        """AC-2: Malformed session cookie passes through (no 500)."""
        transport = ASGITransport(app=test_app)
        async with AsyncClient(
            transport=transport, base_url='http://test'
        ) as ac:
            ac.cookies['session_id'] = 'not-a-uuid'
            resp = await ac.post('/protected')
            assert resp.status_code != 500

    async def test_inactive_session_passes_through(
        self,
        test_app: FastAPI,
    ) -> None:
        """AC-2: Inactive session passes through (validity-first)."""
        session = _make_session(is_active=False)
        repo_patch, db_patch = _patch_session(session)

        with repo_patch, db_patch:
            transport = ASGITransport(app=test_app)
            async with AsyncClient(
                transport=transport, base_url='http://test'
            ) as ac:
                ac.cookies['session_id'] = str(session.id)
                ac.cookies['csrf_token'] = 'valid-token'
                resp = await ac.post('/protected')
                assert resp.status_code != 403
                assert resp.status_code != 500

    async def test_missing_header_or_cookie_returns_403_missing(
        self,
        test_app: FastAPI,
    ) -> None:
        """AC-3: Missing CSRF header/cookie -> 403 csrf_token_missing."""
        session = _make_session()
        repo_patch, db_patch = _patch_session(session)

        with repo_patch, db_patch:
            transport = ASGITransport(app=test_app)
            async with AsyncClient(
                transport=transport, base_url='http://test'
            ) as ac:
                ac.cookies['session_id'] = str(session.id)
                ac.cookies['csrf_token'] = 'some-token'
                resp = await ac.post('/protected')
                assert resp.status_code == 403
                data = resp.json()
                assert data['error_code'] == 'csrf_token_missing'

    async def test_header_cookie_mismatch_returns_403_mismatch(
        self,
        test_app: FastAPI,
    ) -> None:
        """AC-3: Header/cookie mismatch -> 403 csrf_token_mismatch."""
        session = _make_session()
        repo_patch, db_patch = _patch_session(session)

        with repo_patch, db_patch:
            transport = ASGITransport(app=test_app)
            async with AsyncClient(
                transport=transport, base_url='http://test'
            ) as ac:
                ac.cookies['session_id'] = str(session.id)
                ac.cookies['csrf_token'] = 'cookie-token'
                resp = await ac.post(
                    '/protected',
                    headers={'X-CSRF-Token': 'different-token'},
                )
                assert resp.status_code == 403
                data = resp.json()
                assert data['error_code'] == 'csrf_token_mismatch'

    async def test_stored_hash_mismatch_returns_403_mismatch(
        self,
        test_app: FastAPI,
    ) -> None:
        """AC-3: Hash mismatch -> 403 csrf_token_mismatch."""
        session = _make_session(csrf_token_hash='b' * 64)
        repo_patch, db_patch = _patch_session(session)

        with repo_patch, db_patch:
            transport = ASGITransport(app=test_app)
            async with AsyncClient(
                transport=transport, base_url='http://test'
            ) as ac:
                ac.cookies['session_id'] = str(session.id)
                ac.cookies['csrf_token'] = 'some-token'
                resp = await ac.post(
                    '/protected',
                    headers={'X-CSRF-Token': 'some-token'},
                )
                assert resp.status_code == 403
                data = resp.json()
                assert data['error_code'] == 'csrf_token_mismatch'

    async def test_valid_pair_and_hash_passes(
        self,
        test_app: FastAPI,
    ) -> None:
        """AC-3: Valid pair + valid stored hash passes."""
        token_value = 'valid-token'
        token_hash = hashlib.sha256(token_value.encode()).hexdigest()
        session = _make_session(csrf_token_hash=token_hash)
        repo_patch, db_patch = _patch_session(session)

        with repo_patch, db_patch:
            transport = ASGITransport(app=test_app)
            async with AsyncClient(
                transport=transport, base_url='http://test'
            ) as ac:
                ac.cookies['session_id'] = str(session.id)
                ac.cookies['csrf_token'] = token_value
                resp = await ac.post(
                    '/protected',
                    headers={'X-CSRF-Token': token_value},
                )
                assert resp.status_code == 200
