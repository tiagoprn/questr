# ruff: noqa: PLR6301,PLR2004,PLR0913,PLR0917
"""Behavior tests for forgot_password / reset_password (Group FP).

HTTP-boundary tests through ``AsyncClient`` against real PostgreSQL
(testcontainers) and a REAL Redis-backed ``DualRateLimiter`` so the
gate-6 rate limit and gate-7 uniform-response assertions exercise the
actual throttle state machine.
"""

import secrets
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from freezegun import freeze_time
from httpx import AsyncClient, Response
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker

from questr.common.enums import UserStatus
from questr.domains.users.repository import UserRepository
from questr.infrastructure.dual_rate_limiter import (
    DualRateLimiter,
    get_dual_rate_limiter,
)
from questr.infrastructure.email import BaseEmailService, get_email_service

PASSWORD = 'StrongPass1!'
NEW_PASSWORD = 'NewPass1!'
FORGOT_PATH = '/api/v1/auth/forgot-password'
RESET_PATH = '/api/v1/auth/reset-password'
LOGIN_PATH = '/api/v1/auth/login'

T_Maker = async_sessionmaker


def _unique_ip() -> str:
    return f'198.51.100.{secrets.randbelow(250) + 1}'


@pytest_asyncio.fixture
async def real_dual_limiter(redis_url: str) -> DualRateLimiter:
    """Real Redis-backed DualRateLimiter for behavior tests."""
    redis = Redis.from_url(redis_url)
    yield DualRateLimiter(
        redis=redis,
        per_account_max=3,
        per_ip_max=2,
        window_seconds=3600,
    )
    await redis.flushall()
    await redis.aclose()


@pytest_asyncio.fixture
async def app_with_dual_limiter(
    app: object, real_dual_limiter: DualRateLimiter
) -> object:
    """Override the DualRateLimiter with a real Redis-backed one."""
    app.dependency_overrides[get_dual_rate_limiter] = lambda: real_dual_limiter
    return app


async def _signup(
    client: AsyncClient,
    app: object,
    *,
    verify: bool = True,
) -> tuple[str, dict[str, str]]:
    """Signup a user, capturing the reset token, return (email, captured)."""
    suffix = secrets.token_hex(4)
    email = f'fp_{suffix}@example.com'
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
            'username': f'fptest_{suffix}',
            'email': email,
            'first_name': 'Forgot',
            'last_name': 'Password',
            'password': PASSWORD,
            'password_confirmation': PASSWORD,
        },
    )
    assert signup_resp.status_code == 201
    if verify:
        assert 'verify_token' in captured
        vr = await client.get(
            f'/api/v1/auth/verify-email/{captured["verify_token"]}'
        )
        assert vr.status_code == 200
    return signup_resp.json()['email'], captured


async def _forgot(
    client: AsyncClient, email: str, *, ip: str | None = None
) -> Response:
    return await client.post(
        FORGOT_PATH,
        json={'email': email},
        headers={'X-Forwarded-For': ip or _unique_ip()},
    )


async def _reset(
    client: AsyncClient, token: str, password: str = NEW_PASSWORD
) -> Response:
    return await client.post(
        RESET_PATH,
        json={'token': token, 'new_password': password},
    )


async def _login(
    client: AsyncClient, email: str, password: str = PASSWORD
) -> Response:
    return await client.post(
        LOGIN_PATH,
        json={'email': email, 'password': password},
        headers={'X-Forwarded-For': _unique_ip()},
    )


class TestForgotPasswordFlow:
    """End-to-end forgot/reset flow through the HTTP boundary."""

    @pytest.mark.asyncio
    async def test_full_reset_flow(
        self, client: AsyncClient, app_with_dual_limiter: object
    ) -> None:
        """Forgot -> reset -> re-login with the new password."""
        email, captured = await _signup(client, app_with_dual_limiter)

        resp = await _forgot(client, email)
        assert resp.status_code == 200
        assert 'message' in resp.json()
        assert 'reset_token' in captured

        reset_resp = await _reset(client, captured['reset_token'])
        assert reset_resp.status_code == 200
        assert reset_resp.json()['message'] == 'Password reset successfully'

        relogin = await _login(client, email, NEW_PASSWORD)
        assert relogin.status_code == 200

    @pytest.mark.asyncio
    async def test_unknown_email_is_uniform_200(
        self, client: AsyncClient, app_with_dual_limiter: object
    ) -> None:
        """Gate 7: unknown email returns the same 200 as a known one."""
        resp = await _forgot(client, 'nobody@example.com')
        assert resp.status_code == 200
        assert 'message' in resp.json()

    @pytest.mark.asyncio
    async def test_rate_limit_429(
        self, client: AsyncClient, app_with_dual_limiter: object
    ) -> None:
        """Gate 6: exceeding the per-account limit returns 429."""
        email, _ = await _signup(client, app_with_dual_limiter)
        # Distinct IPs isolate the per-IP window so the per-account cap
        # (3) is what trips on the 4th request.
        for _ in range(3):
            resp = await _forgot(client, email)
            assert resp.status_code == 200
        limited = await _forgot(client, email)
        assert limited.status_code == 429
        assert limited.json()['error_code'] == 'rate_limited'

    @pytest.mark.asyncio
    async def test_pending_account_resends_verification(
        self, client: AsyncClient, app_with_dual_limiter: object
    ) -> None:
        """Matrix D3: PENDING resends verification, no reset token."""
        email, captured = await _signup(
            client, app_with_dual_limiter, verify=False
        )
        captured.pop('reset_token', None)
        resp = await _forgot(client, email)
        assert resp.status_code == 200
        assert 'reset_token' not in captured
        assert 'verify_token' in captured

    @pytest.mark.asyncio
    async def test_suspended_account_sends_nothing(
        self,
        client: AsyncClient,
        app_with_dual_limiter: object,
        db_session_maker: T_Maker,
    ) -> None:
        """Matrix D3: SUSPENDED sends nothing, uniform 200."""
        email, captured = await _signup(client, app_with_dual_limiter)
        async with db_session_maker() as session:
            user = await UserRepository(session).get_by_email(email)
            assert user is not None
            assert user.id is not None
            await UserRepository(session).update_status(
                user.id, UserStatus.SUSPENDED
            )
            await session.commit()

        captured.pop('reset_token', None)
        resp = await _forgot(client, email)
        assert resp.status_code == 200
        assert 'reset_token' not in captured

    @pytest.mark.asyncio
    async def test_expired_token_rejected(
        self, client: AsyncClient, app_with_dual_limiter: object
    ) -> None:
        """An expired reset token is rejected with a recovery hint."""
        email, captured = await _signup(client, app_with_dual_limiter)

        with freeze_time('2026-03-01 12:00:00') as frozen:
            await _forgot(client, email)
            assert 'reset_token' in captured
            frozen.move_to(datetime(2026, 3, 1, 13, 1, tzinfo=timezone.utc))
            resp = await _reset(client, captured['reset_token'])
        assert resp.status_code == 400
        assert resp.json()['recovery'] == ['forgot_password']
