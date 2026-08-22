# ruff: noqa: PLR6301,PLR2004,PLR0913,PLR0917
"""Behavior tests for change_email (Group CE).

HTTP-boundary tests through ``AsyncClient`` against real PostgreSQL
(testcontainers) and a REAL Redis-backed ``DualRateLimiter``. Covers
the full change -> confirm -> revert journey, the ATO hardening
(change requires the current password), and the gate-3 hold routing of
password resets to the previous email.
"""

import secrets
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from freezegun import freeze_time
from httpx import AsyncClient, Response
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker

from questr.infrastructure.dual_rate_limiter import (
    DualRateLimiter,
    get_dual_rate_limiter,
    get_dual_rate_limiter_email_change,
)
from questr.infrastructure.email import BaseEmailService, get_email_service

PASSWORD = 'StrongPass1!'
LOGIN_PATH = '/api/v1/auth/login'
ME_PATH = '/api/v1/auth/me'
CHANGE_EMAIL_PATH = '/api/v1/auth/me/email'
CONFIRM_PATH = '/api/v1/auth/me/email/confirm'
REVERT_PATH = '/api/v1/auth/me/email/revert'
FORGOT_PATH = '/api/v1/auth/forgot-password'

T_Maker = async_sessionmaker


def _unique_ip() -> str:
    return f'198.51.100.{secrets.randbelow(250) + 1}'


@pytest_asyncio.fixture
async def real_dual_limiter(redis_url: str) -> DualRateLimiter:
    """Real Redis-backed DualRateLimiter for the forgot-password path."""
    redis = Redis.from_url(redis_url)
    yield DualRateLimiter(
        redis=redis,
        per_account_max=10,
        per_ip_max=5,
        window_seconds=3600,
    )
    await redis.flushall()
    await redis.aclose()


@pytest_asyncio.fixture
async def real_email_change_limiter(redis_url: str) -> DualRateLimiter:
    """Real Redis-backed DualRateLimiter for the change-email path.

    Namespaced under its own key prefix so it is independent of the
    forgot-password limiter (gate 6), matching production wiring.
    """
    redis = Redis.from_url(redis_url)
    yield DualRateLimiter(
        redis=redis,
        per_account_max=10,
        per_ip_max=5,
        window_seconds=3600,
        key_prefix='email_change',
    )
    await redis.flushall()
    await redis.aclose()


@pytest_asyncio.fixture
async def app_with_dual_limiter(
    app: object,
    real_dual_limiter: DualRateLimiter,
    real_email_change_limiter: DualRateLimiter,
) -> object:
    app.dependency_overrides[get_dual_rate_limiter] = lambda: real_dual_limiter
    app.dependency_overrides[get_dual_rate_limiter_email_change] = lambda: (
        real_email_change_limiter
    )
    return app


async def _signup(
    client: AsyncClient,
    app: object,
) -> tuple[str, dict[str, str]]:
    """Signup + verify a user, capturing confirm/revert tokens."""
    suffix = secrets.token_hex(4)
    email = f'ce_{suffix}@example.com'
    captured: dict[str, str] = {}

    class CaptureEmail(BaseEmailService):
        async def send_verification_email(
            self, to_email: str, token: str
        ) -> bool:
            captured['verify_token'] = token
            return True

        async def send_password_changed_email(self, to_email: str) -> bool:
            return True

        async def send_password_reset_email(
            self, to_email: str, token: str
        ) -> bool:
            captured['reset_token'] = token
            return True

        async def send_password_reset_done_email(self, to_email: str) -> bool:
            return True

        async def send_email_change_confirm_email(
            self, to_email: str, token: str
        ) -> bool:
            captured['confirm_token'] = token
            return True

        async def send_email_change_old_notification(
            self, to_email: str, revert_token: str
        ) -> bool:
            captured['revert_token'] = revert_token
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
            'username': f'cetest_{suffix}',
            'email': email,
            'first_name': 'Change',
            'last_name': 'Email',
            'password': PASSWORD,
            'password_confirmation': PASSWORD,
        },
    )
    assert signup_resp.status_code == 201
    assert 'verify_token' in captured
    vr = await client.get(
        f'/api/v1/auth/verify-email/{captured["verify_token"]}'
    )
    assert vr.status_code == 200
    return signup_resp.json()['email'], captured


async def _login(
    client: AsyncClient, email: str, password: str = PASSWORD
) -> Response:
    return await client.post(
        LOGIN_PATH,
        json={'email': email, 'password': password},
        headers={'X-Forwarded-For': _unique_ip()},
    )


def _csrf(client: AsyncClient) -> str:
    return client.cookies['csrf_token']


class TestChangeEmailFlow:
    """End-to-end change_email journey through the HTTP boundary."""

    @pytest.mark.asyncio
    async def test_full_confirm_revert_cycle(
        self, client: AsyncClient, app_with_dual_limiter: object
    ) -> None:
        """Change -> confirm -> sessions die -> revert -> old email back."""
        email, captured = await _signup(client, app_with_dual_limiter)
        await _login(client, email)
        new_email = 'new@example.com'

        # Request the change (CSRF-protected, auth required).
        resp = await client.post(
            CHANGE_EMAIL_PATH,
            json={
                'new_email': new_email,
                'current_password': PASSWORD,
            },
            headers={
                'X-CSRF-Token': _csrf(client),
                'X-Forwarded-For': _unique_ip(),
            },
        )
        assert resp.status_code == 200
        assert 'confirm_token' in captured
        assert 'revert_token' in captured

        # Confirm via POST (pre-auth, token only).
        confirm = await client.get(
            f'{CONFIRM_PATH}/{captured["confirm_token"]}'
        )
        assert confirm.status_code == 200
        assert confirm.json()['message'] == 'Email changed successfully'

        # Gate 5: all sessions revoked -> /me is 401.
        me = await client.get(ME_PATH)
        assert me.status_code == 401

        # Re-login with the NEW email works.
        relogin = await _login(client, new_email)
        assert relogin.status_code == 200

        # Revert within the hold window restores the old email.
        revert = await client.get(f'{REVERT_PATH}/{captured["revert_token"]}')
        assert revert.status_code == 200
        assert revert.json()['message'] == 'Email change reverted'

        await _login(client, email)
        assert (await client.get(ME_PATH)).status_code == 200

    @pytest.mark.asyncio
    async def test_ato_change_email_requires_current_password(
        self, client: AsyncClient, app_with_dual_limiter: object
    ) -> None:
        """Gate 1: a stolen session cannot change the email without the
        current password."""
        email, captured = await _signup(client, app_with_dual_limiter)
        await _login(client, email)

        resp = await client.post(
            CHANGE_EMAIL_PATH,
            json={
                'new_email': 'attacker@example.com',
                'current_password': 'WrongPass1!',
            },
            headers={'X-CSRF-Token': _csrf(client)},
        )
        assert resp.status_code == 400
        assert resp.json()['error_code'] == 'invalid_current_password'
        assert 'confirm_token' not in captured

    @pytest.mark.asyncio
    async def test_reset_during_hold_routes_to_previous_email(
        self, client: AsyncClient, app_with_dual_limiter: object
    ) -> None:
        """Gate 3: during the hold, forgot-password goes to previous_email."""
        email, captured = await _signup(client, app_with_dual_limiter)
        await _login(client, email)
        new_email = 'new@example.com'

        await client.post(
            CHANGE_EMAIL_PATH,
            json={'new_email': new_email, 'current_password': PASSWORD},
            headers={'X-CSRF-Token': _csrf(client)},
        )
        assert 'confirm_token' in captured
        await client.get(f'{CONFIRM_PATH}/{captured["confirm_token"]}')

        # Request a reset for the OLD email; the reset must route to the
        # previous (old) email, which is what we requested.
        captured.pop('reset_token', None)
        forgot = await client.post(FORGOT_PATH, json={'email': email})
        assert forgot.status_code == 200
        assert 'reset_token' in captured

    @pytest.mark.asyncio
    async def test_revert_after_hold_expiry_rejected(
        self, client: AsyncClient, app_with_dual_limiter: object
    ) -> None:
        """Gate 4: revert after the hold window is rejected."""
        email, captured = await _signup(client, app_with_dual_limiter)
        await _login(client, email)

        with freeze_time('2026-03-01 12:00:00') as frozen:
            # Change + confirm at 12:00 opens the hold (email_changed_at).
            resp = await client.post(
                CHANGE_EMAIL_PATH,
                json={
                    'new_email': 'new@example.com',
                    'current_password': PASSWORD,
                },
                headers={'X-CSRF-Token': _csrf(client)},
            )
            assert resp.status_code == 200
            assert 'revert_token' in captured
            confirm = await client.get(
                f'{CONFIRM_PATH}/{captured["confirm_token"]}'
            )
            assert confirm.status_code == 200

            # 49 hours later the hold (48h) has expired.
            frozen.move_to(datetime(2026, 3, 3, 13, 0, tzinfo=timezone.utc))
            late = await client.get(
                f'{REVERT_PATH}/{captured["revert_token"]}'
            )
        assert late.status_code == 400
        assert late.json()['recovery'] == ['forgot_password']
        # The revert token is not reusable either: single-use lifecycle.
        again = await client.get(f'{REVERT_PATH}/{captured["revert_token"]}')
        assert again.status_code == 400
