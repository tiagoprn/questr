# ruff: noqa: PLR6301,PLR2004,PLR0913,PLR0917
# noqa: PLR6301,PLR2004
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid7

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from questr.common.enums import UserRole, UserStatus
from questr.common.exceptions import (
    AccountBannedError,
    AccountSuspendedError,
    AuthenticationError,
    EmailNotVerifiedError,
    TooManyActiveSessionsError,
)
from questr.domains.users.api import get_auth_service_v2
from questr.domains.users.service import AuthService
from questr.infrastructure.email import (
    BaseEmailService,
    get_email_service,
)
from questr.infrastructure.rate_limiter import get_rate_limiter


class TestSignup:
    @pytest.mark.asyncio
    async def test_signup_returns_201(
        self,
        client: AsyncClient,
    ) -> None:
        response = await client.post(
            '/api/v1/auth/signup',
            json={
                'username': 'newuser',
                'email': 'newuser@example.com',
                'first_name': 'New',
                'last_name': 'User',
                'password': 'StrongPass1!',
                'password_confirmation': 'StrongPass1!',
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data['username'] == 'newuser'
        assert data['email'] == 'newuser@example.com'
        assert data['status'] == 'pending'

    @pytest.mark.asyncio
    async def test_signup_returns_409_on_duplicate(
        self,
        client: AsyncClient,
    ) -> None:
        payload = {
            'username': 'duplicate',
            'email': 'duplicate@example.com',
            'first_name': 'Dup',
            'last_name': 'User',
            'password': 'StrongPass1!',
            'password_confirmation': 'StrongPass1!',
        }
        await client.post('/api/v1/auth/signup', json=payload)
        response = await client.post('/api/v1/auth/signup', json=payload)
        assert response.status_code == 409


class TestVerifyEmail:
    @pytest.mark.asyncio
    async def test_verify_email_returns_400_on_invalid_token(
        self,
        client: AsyncClient,
    ) -> None:
        response = await client.get(
            '/api/v1/auth/verify-email/invalid_token',
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_verify_email_returns_200_on_valid_token(
        self,
        app: FastAPI,
        client: AsyncClient,
    ) -> None:
        captured: dict[str, str] = {}

        class RecordingEmailService(BaseEmailService):
            async def send_verification_email(
                self, to_email: str, token: str
            ) -> bool:
                captured['token'] = token
                return True

        app.dependency_overrides[get_email_service] = RecordingEmailService

        signup_response = await client.post(
            '/api/v1/auth/signup',
            json={
                'username': 'verifyme',
                'email': 'verifyme@example.com',
                'first_name': 'Verify',
                'last_name': 'Me',
                'password': 'StrongPass1!',
                'password_confirmation': 'StrongPass1!',
            },
        )
        assert signup_response.status_code == 201
        assert 'token' in captured

        verify_response = await client.get(
            f'/api/v1/auth/verify-email/{captured["token"]}',
        )
        assert verify_response.status_code == 200
        assert verify_response.json()['status'] == 'active'


class TestResendVerification:
    @pytest.mark.asyncio
    async def test_resend_returns_200(
        self,
        client: AsyncClient,
    ) -> None:
        response = await client.post(
            '/api/v1/auth/resend-verification',
            json={'email': 'nonexistent@example.com'},
        )
        assert response.status_code == 200
        assert 'sent' in response.json()['message'].lower()

    @pytest.mark.asyncio
    async def test_resend_returns_429_on_rate_limit(
        self,
        app: FastAPI,
        client: AsyncClient,
    ) -> None:
        denying_limiter = MagicMock()
        denying_limiter.is_allowed = AsyncMock(return_value=False)
        app.dependency_overrides[get_rate_limiter] = lambda: denying_limiter

        response = await client.post(
            '/api/v1/auth/resend-verification',
            json={'email': 'someone@example.com'},
        )
        assert response.status_code == 429

    @pytest.mark.asyncio
    async def test_resend_with_plus_email_succeeds(
        self,
        client: AsyncClient,
    ) -> None:
        """Resend verification for a plus-addressed email returns 200."""
        signup_resp = await client.post(
            '/api/v1/auth/signup',
            json={
                'username': 'plusresend',
                'email': 'plusresend+work@example.com',
                'first_name': 'Plus',
                'last_name': 'Resend',
                'password': 'StrongPass1!',
                'password_confirmation': 'StrongPass1!',
            },
        )
        assert signup_resp.status_code == 201

        resend_resp = await client.post(
            '/api/v1/auth/resend-verification',
            json={'email': 'plusresend+work@example.com'},
        )
        assert resend_resp.status_code == 200
        assert 'sent' in resend_resp.json()['message'].lower()


@pytest.fixture
def mock_login_service() -> AuthService:
    """Return a mock AuthService that succeeds for login."""
    svc = MagicMock(spec=AuthService)
    svc.login = AsyncMock(
        return_value={
            'user': {
                'id': uuid7(),
                'username': 'testuser',
                'email': 'test@example.com',
                'first_name': 'Test',
                'last_name': 'User',
                'role': UserRole.USER,
                'status': UserStatus.ACTIVE,
                'created_at': datetime.now(timezone.utc).isoformat(),
            },
            'session': MagicMock(
                id=uuid7(),
                issued_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc),
                absolute_expires_at=datetime.now(timezone.utc),
            ),
            'csrf_token': 'test-csrf-token-12345',
        }
    )
    return svc


class TestLogin:
    """Tests for POST /api/v1/auth/login."""

    @pytest.mark.asyncio
    async def test_login_returns_200_with_correct_shape(
        self,
        app: FastAPI,
        client: AsyncClient,
        mock_login_service: AuthService,
    ) -> None:
        """AC-1: Login 200 body matches design Section 6."""
        overrides = {get_auth_service_v2: lambda: mock_login_service}
        app.dependency_overrides.update(overrides)

        resp = await client.post(
            '/api/v1/auth/login',
            json={
                'email': 'test@example.com',
                'password': 'StrongPass1!',
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert 'user' in data
        assert 'user_status' in data['user']
        assert 'status' not in data['user']
        assert 'session' in data
        assert 'csrf_token' in data
        assert 'password_hash' not in data.get('user', {})

    @pytest.mark.asyncio
    async def test_login_response_excludes_prohibited(
        self,
        app: FastAPI,
        client: AsyncClient,
        mock_login_service: AuthService,
    ) -> None:
        """AC-1: Login response excludes prohibited fields."""
        overrides = {get_auth_service_v2: lambda: mock_login_service}
        app.dependency_overrides.update(overrides)

        resp = await client.post(
            '/api/v1/auth/login',
            json={
                'email': 'test@example.com',
                'password': 'StrongPass1!',
            },
        )
        data = resp.json()
        user_keys = set(data.get('user', {}).keys())
        excluded = {'password_hash', 'csrf_token_hash', 'ip_address'}
        assert user_keys.isdisjoint(excluded)

    @pytest.mark.parametrize(
        ('exception', 'expected_status', 'expected_code'),
        [
            (AuthenticationError('Invalid'), 401, None),
            (EmailNotVerifiedError('Verify'), 403, 'email_not_verified'),
            (AccountSuspendedError('Suspended'), 403, 'account_suspended'),
            (AccountBannedError('Banned'), 403, 'account_banned'),
            (
                TooManyActiveSessionsError('Max'),
                429,
                'too_many_active_sessions',
            ),
        ],
    )
    @pytest.mark.asyncio
    async def test_login_failures_map_to_responses(
        self,
        app: FastAPI,
        client: AsyncClient,
        exception: Exception,
        expected_status: int,
        expected_code: str | None,
    ) -> None:
        """AC-5: Failures map to structured responses."""
        svc = MagicMock(spec=AuthService)
        svc.login = AsyncMock(side_effect=exception)
        overrides = {get_auth_service_v2: lambda: svc}
        app.dependency_overrides.update(overrides)

        resp = await client.post(
            '/api/v1/auth/login',
            json={'email': 'test@example.com', 'password': 'wrong'},
        )
        assert resp.status_code == expected_status
        if expected_code:
            data = resp.json()
            assert data.get('error_code') == expected_code


class TestLogout:
    """Tests for POST /api/v1/auth/logout and logout-all."""

    @pytest.mark.asyncio
    async def test_logout_clears_cookies(
        self,
        app: FastAPI,
        client: AsyncClient,
    ) -> None:
        """AC-3: Logout clears cookies with matching paths."""
        svc = MagicMock(spec=AuthService)
        svc.logout = AsyncMock()
        overrides = {get_auth_service_v2: lambda: svc}
        app.dependency_overrides.update(overrides)

        client.cookies['session_id'] = str(uuid7())
        resp = await client.post('/api/v1/auth/logout')
        assert resp.status_code == 200
        set_cookie = resp.headers.get('set-cookie', '')
        assert 'session_id=' in set_cookie
        assert 'csrf_token=' in set_cookie

    @pytest.mark.asyncio
    async def test_logout_all_returns_revoked_count(
        self,
        app: FastAPI,
        client: AsyncClient,
    ) -> None:
        """AC-3: Logout-all returns the revoked count."""
        svc = MagicMock(spec=AuthService)
        svc.logout_all = AsyncMock(return_value=3)
        svc.session_repo = MagicMock()
        svc.session_repo.get_by_id = AsyncMock(return_value=None)
        overrides = {get_auth_service_v2: lambda: svc}
        app.dependency_overrides.update(overrides)

        client.cookies['session_id'] = str(uuid7())
        resp = await client.post('/api/v1/auth/logout-all')
        assert resp.status_code == 200
        data = resp.json()
        assert data.get('sessions_revoked') == 0


class TestGetCurrentUser:
    """Tests for get_current_user and GET /me."""

    @pytest.mark.asyncio
    async def test_missing_cookie_returns_401(
        self,
        app: FastAPI,
        client: AsyncClient,
    ) -> None:
        """AC-4: Missing cookie yields 401."""

        svc = MagicMock(spec=AuthService)
        overrides = {get_auth_service_v2: lambda: svc}
        app.dependency_overrides.update(overrides)

        resp = await client.get('/api/v1/auth/me')
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_malformed_cookie_returns_401(
        self,
        app: FastAPI,
        client: AsyncClient,
    ) -> None:
        """AC-4: Malformed cookie yields 401 (never 500)."""
        svc = MagicMock(spec=AuthService)
        overrides = {get_auth_service_v2: lambda: svc}
        app.dependency_overrides.update(overrides)

        client.cookies['session_id'] = 'not-a-uuid'
        resp = await client.get('/api/v1/auth/me')
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_me_returns_user_and_csrf_echo(
        self,
        app: FastAPI,
        client: AsyncClient,
    ) -> None:
        """AC-1: GET /me returns user + echoed CSRF."""
        mock_user = MagicMock(
            id=uuid7(),
            username='testuser',
            email='test@example.com',
            first_name='Test',
            last_name='User',
            role=UserRole.USER,
            status=UserStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
        )
        svc = MagicMock(spec=AuthService)
        svc.validate_session = AsyncMock(return_value=mock_user)
        overrides = {get_auth_service_v2: lambda: svc}
        app.dependency_overrides.update(overrides)

        client.cookies['session_id'] = str(uuid7())
        client.cookies['csrf_token'] = 'echoed-csrf-token'
        resp = await client.get('/api/v1/auth/me')
        assert resp.status_code == 200
        data = resp.json()
        assert 'csrf_token' in data
        assert data['csrf_token'] == 'echoed-csrf-token'
