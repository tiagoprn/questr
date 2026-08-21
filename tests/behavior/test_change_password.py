# ruff: noqa: PLR6301,PLR2004,PLR0913,PLR0917
"""Behavior tests for change_password (Group CP).

HTTP-boundary tests through ``AsyncClient`` against real PostgreSQL
(testcontainers) and a REAL Redis-backed ``LoginRateLimiter`` so the
gate-1 current-password lockout exercises the actual throttle state
machine. Each helper sends a unique ``X-Forwarded-For`` IP per test to
isolate per-IP windows.
"""

import secrets
from datetime import datetime, timezone

import pytest
from freezegun import freeze_time
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.ext.asyncio import async_sessionmaker

from questr.domains.users.repository import UserRepository
from questr.domains.users.service import verify_password
from questr.infrastructure.email import BaseEmailService, get_email_service

PASSWORD = 'StrongPass1!'
WRONG_PASSWORD = 'WrongPass1!'
LOGIN_PATH = '/api/v1/auth/login'
ME_PATH = '/api/v1/auth/me'
CHANGE_PASSWORD_PATH = '/api/v1/auth/me/password'

T_Maker = async_sessionmaker


def _unique_ip() -> str:
    """Unique TEST-NET-2 IP per call, isolating per-IP throttle windows."""
    return f'198.51.100.{secrets.randbelow(250) + 1}'


async def _signup(client: AsyncClient, app: object) -> str:
    """Signup and verify a user, returning the stored email."""
    suffix = secrets.token_hex(4)
    email = f'cp_{suffix}@example.com'
    captured: dict[str, str] = {}

    class CaptureEmail(BaseEmailService):
        async def send_verification_email(
            self, to_email: str, token: str
        ) -> bool:
            captured['token'] = token
            return True

        async def send_password_changed_email(self, to_email: str) -> bool:
            return True

        async def send_password_reset_email(
            self, to_email: str, token: str
        ) -> bool:
            return True

        async def send_password_reset_done_email(self, to_email: str) -> bool:
            return True

        async def send_email_change_confirm_email(
            self, to_email: str, token: str
        ) -> bool:
            return True

        async def send_email_change_old_notification(
            self, to_email: str, revert_token: str
        ) -> bool:
            return True

        async def send_email_changed_notice(self, to_email: str) -> bool:
            return True

        async def send_email_change_reverted_notice(
            self, to_email: str
        ) -> bool:
            return True

    app.dependency_overrides[get_email_service] = CaptureEmail

    signup_resp = await client.post(
        '/api/v1/auth/signup',
        json={
            'username': f'cptest_{suffix}',
            'email': email,
            'first_name': 'Change',
            'last_name': 'Password',
            'password': PASSWORD,
            'password_confirmation': PASSWORD,
        },
    )
    assert signup_resp.status_code == 201
    assert 'token' in captured
    verify_resp = await client.get(
        f'/api/v1/auth/verify-email/{captured["token"]}'
    )
    assert verify_resp.status_code == 200
    return signup_resp.json()['email']


async def _login(
    client: AsyncClient,
    email: str,
    password: str = PASSWORD,
    *,
    ip: str | None = None,
) -> Response:
    return await client.post(
        LOGIN_PATH,
        json={'email': email, 'password': password},
        headers={'X-Forwarded-For': ip or _unique_ip()},
    )


def _csrf(client: AsyncClient) -> str:
    return client.cookies['csrf_token']


async def _change_password(
    client: AsyncClient,
    current: str,
    new: str,
    *,
    ip: str | None = None,
) -> Response:
    return await client.post(
        CHANGE_PASSWORD_PATH,
        json={'current_password': current, 'new_password': new},
        headers={
            'X-CSRF-Token': _csrf(client),
            'X-Forwarded-For': ip or _unique_ip(),
        },
    )


class TestChangePasswordFlow:
    """End-to-end change_password through the HTTP boundary."""

    @pytest.mark.asyncio
    async def test_change_password_revokes_other_sessions_and_relogin(
        self, client: AsyncClient, app: object
    ) -> None:
        """Gate 5: other sessions die, current kept; re-login with new."""
        email = await _signup(client, app)

        # Session 1 (the client fixture).
        r1 = await _login(client, email)
        assert r1.status_code == 200

        # Session 2 on a separate client.
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url='https://test'
        ) as client2:
            r2 = await _login(client2, email)
            assert r2.status_code == 200

            resp = await _change_password(client, PASSWORD, 'NewPass1!')
            assert resp.status_code == 200
            assert resp.json()['message'] == 'Password changed'

            # Session 2 was revoked: its cookie now yields 401.
            me2 = await client2.get(ME_PATH)
            assert me2.status_code == 401

        # Session 1 was kept: still authenticated.
        me1 = await client.get(ME_PATH)
        assert me1.status_code == 200

        # Re-login with the new password succeeds.
        relogin = await _login(client, email, 'NewPass1!')
        assert relogin.status_code == 200

    @pytest.mark.asyncio
    async def test_wrong_current_password_lockout(
        self, client: AsyncClient, app: object
    ) -> None:
        """Gate 1: repeated wrong current password triggers lockout."""
        email = await _signup(client, app)
        await _login(client, email)
        ip = _unique_ip()

        with freeze_time('2026-03-01 12:00:00') as frozen:
            for _ in range(5):
                resp = await _change_password(
                    client, WRONG_PASSWORD, 'NewPass1!', ip=ip
                )
                assert resp.status_code == 400
                assert resp.json()['error_code'] == 'invalid_current_password'

            locked = await _change_password(
                client, WRONG_PASSWORD, 'NewPass1!', ip=ip
            )
            assert locked.status_code == 429
            assert locked.json()['error_code'] == 'rate_limited'

            # Even the correct current password is rejected while locked.
            still = await _change_password(
                client, PASSWORD, 'NewPass1!', ip=ip
            )
            assert still.status_code == 429

            frozen.move_to(datetime(2026, 3, 1, 12, 31, tzinfo=timezone.utc))
            ok = await _change_password(client, PASSWORD, 'NewPass1!', ip=ip)
            assert ok.status_code == 200

    @pytest.mark.asyncio
    async def test_weak_new_password_is_400(
        self, client: AsyncClient, app: object
    ) -> None:
        """T-003: a weak new password returns 400, not 500."""
        email = await _signup(client, app)
        await _login(client, email)
        resp = await _change_password(client, PASSWORD, 'short')
        assert resp.status_code == 400
        assert 'at least 8 characters' in resp.json()['detail']

    @pytest.mark.asyncio
    async def test_missing_csrf_header_is_403(
        self, client: AsyncClient, app: object
    ) -> None:
        """CSRF auto-protection: missing header -> 403 on me/password."""
        email = await _signup(client, app)
        await _login(client, email)
        resp = await client.post(
            CHANGE_PASSWORD_PATH,
            json={'current_password': PASSWORD, 'new_password': 'NewPass1!'},
        )
        assert resp.status_code == 403
        assert resp.json()['error_code'] == 'csrf_token_missing'

    @pytest.mark.asyncio
    async def test_mismatched_csrf_header_is_403(
        self, client: AsyncClient, app: object
    ) -> None:
        """CSRF auto-protection: mismatched header -> 403 on me/password."""
        email = await _signup(client, app)
        await _login(client, email)
        resp = await client.post(
            CHANGE_PASSWORD_PATH,
            json={'current_password': PASSWORD, 'new_password': 'NewPass1!'},
            headers={'X-CSRF-Token': 'bogus'},
        )
        assert resp.status_code == 403
        assert resp.json()['error_code'] == 'csrf_token_mismatch'

    @pytest.mark.asyncio
    async def test_password_hash_updated(
        self,
        client: AsyncClient,
        app: object,
        db_session_maker: T_Maker,
    ) -> None:
        """The stored hash reflects the new password."""
        email = await _signup(client, app)
        await _login(client, email)
        resp = await _change_password(client, PASSWORD, 'NewPass1!')
        assert resp.status_code == 200

        async with db_session_maker() as session:
            user = await UserRepository(session).get_by_email(email)
        assert user is not None
        assert verify_password('NewPass1!', user.password_hash)
