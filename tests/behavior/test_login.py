# ruff: noqa: PLR6301,PLR2004,PLR0913,PLR0917
"""Behavior tests for the login feature — design §15 matrix.

HTTP-boundary tests through ``AsyncClient`` against real PostgreSQL
(testcontainers) and a REAL Redis-backed ``LoginRateLimiter`` (see
``tests/behavior/conftest.py``) so FR-006/FR-007 assertions exercise
the actual throttle state machine.

Every login helper sends a unique ``X-Forwarded-For`` IP per test to
keep the per-IP sliding window isolated even within one test module.
"""

import logging
import secrets
import statistics
import time
from collections.abc import Coroutine
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import pytest
from freezegun import freeze_time
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from questr.common.enums import UserStatus
from questr.domains.users.repository import (
    Session,
    SessionRepository,
    UserRepository,
)
from questr.domains.users.service import hash_password, verify_password
from questr.infrastructure.email import BaseEmailService, get_email_service
from questr.infrastructure.login_rate_limiter import LoginRateLimiter

PASSWORD = 'StrongPass1!'
WRONG_PASSWORD = 'WrongPass1!'
LOGIN_PATH = '/api/v1/auth/login'
LOGOUT_PATH = '/api/v1/auth/logout'
LOGOUT_ALL_PATH = '/api/v1/auth/logout-all'
ME_PATH = '/api/v1/auth/me'

T_Maker = async_sessionmaker[AsyncSession]


def _unique_ip() -> str:
    """Unique TEST-NET-2 IP per call, isolating per-IP throttle windows."""
    return f'198.51.100.{secrets.randbelow(250) + 1}'


async def _signup(
    client: AsyncClient,
    app: object,
    *,
    verify: bool = True,
    local_part: str = 'login_test',
    domain: str = 'example.com',
) -> str:
    """Signup a user, optionally verify the email, return stored email."""
    suffix = secrets.token_hex(4)
    email = f'{local_part}_{suffix}@{domain}'
    captured: dict[str, str] = {}

    class CaptureEmail(BaseEmailService):
        async def send_verification_email(
            self, to_email: str, token: str
        ) -> bool:
            captured['token'] = token
            return True

    app.dependency_overrides[get_email_service] = CaptureEmail

    signup_resp = await client.post(
        '/api/v1/auth/signup',
        json={
            'username': f'logintest_{suffix}',
            'email': email,
            'first_name': 'Login',
            'last_name': 'Test',
            'password': PASSWORD,
            'password_confirmation': PASSWORD,
        },
    )
    assert signup_resp.status_code == 201

    if verify:
        assert 'token' in captured
        verify_resp = await client.get(
            f'/api/v1/auth/verify-email/{captured["token"]}'
        )
        assert verify_resp.status_code == 200
        assert verify_resp.json()['status'] == 'active'
    # The response carries the normalized (stored) form of the email.
    return signup_resp.json()['email']


async def _login(
    client: AsyncClient,
    email: str,
    password: str = PASSWORD,
    *,
    ip: str | None = None,
    remember_me: bool | None = None,
) -> Response:
    payload: dict[str, object] = {'email': email, 'password': password}
    if remember_me is not None:
        payload['remember_me'] = remember_me
    return await client.post(
        LOGIN_PATH,
        json=payload,
        headers={'X-Forwarded-For': ip or _unique_ip()},
    )


def _csrf(client: AsyncClient) -> str:
    return client.cookies['csrf_token']


async def _set_status(maker: T_Maker, email: str, status: UserStatus) -> None:
    async with maker() as session:
        repo = UserRepository(session)
        user = await repo.get_by_email(email)
        assert user is not None
        assert user.id is not None
        await repo.update_status(user.id, status)
        await session.commit()


async def _get_session_row(maker: T_Maker, session_id: UUID) -> Session:
    async with maker() as session:
        row = await SessionRepository(session).get_by_id(session_id)
    assert row is not None
    return row


async def _seed_sessions(maker: T_Maker, email: str, count: int) -> None:
    """Create ``count`` active sessions for ``email`` directly in the DB."""
    async with maker() as session:
        user = await UserRepository(session).get_by_email(email)
        assert user is not None
        assert user.id is not None
        repo = SessionRepository(session)
        now = datetime.now(timezone.utc)
        for _ in range(count):
            await repo.create(
                Session(
                    user_id=user.id,
                    issued_at=now,
                    last_activity=now,
                    expires_at=now + timedelta(minutes=30),
                    absolute_expires_at=now + timedelta(hours=8),
                    remember_me=False,
                    ip_address='198.51.100.1',
                    user_agent='seed',
                    csrf_token_hash='0' * 64,
                    is_active=True,
                )
            )
        await session.commit()


def _set_cookie_headers(resp: Response, name: str) -> str:
    """Return the Set-Cookie header for ``name`` from a response."""
    for header in resp.headers.get_list('set-cookie'):
        if header.startswith(f'{name}='):
            return header
    raise AssertionError(f'no Set-Cookie header for {name}')


class TestLoginFlow:
    """End-to-end login flow through the HTTP boundary."""

    @pytest.mark.asyncio
    async def test_happy_path_and_response_contract(
        self, client: AsyncClient, app: object
    ) -> None:
        """Happy path: signup -> verify -> login."""
        email = await _signup(client, app)
        login_resp = await _login(client, email)
        assert login_resp.status_code == 200
        data = login_resp.json()
        assert 'user' in data
        assert data['user']['user_status'] == 'active'
        assert data['user']['created_at'] is not None
        assert 'session' in data
        # FR-012: token_urlsafe(32) yields ~43 URL-safe characters.
        assert len(data['csrf_token']) == 43

    @pytest.mark.asyncio
    async def test_wrong_password_returns_401(
        self, client: AsyncClient, app: object
    ) -> None:
        """Wrong password returns generic 401."""
        email = await _signup(client, app)
        resp = await _login(client, email, WRONG_PASSWORD)
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_unknown_email_body_matches_wrong_password(
        self, client: AsyncClient, app: object
    ) -> None:
        """FR-003: unknown email and wrong password are identical 401s."""
        email = await _signup(client, app)
        unknown = await _login(client, f'ghost_{email}', WRONG_PASSWORD)
        wrong = await _login(client, email, WRONG_PASSWORD)
        assert unknown.status_code == 401
        assert wrong.status_code == 401
        assert unknown.json() == wrong.json()
        assert unknown.json()['detail'] == 'Invalid email or password'

    @pytest.mark.asyncio
    async def test_malformed_cookie_is_401(self, client: AsyncClient) -> None:
        """Malformed session cookie yields 401."""
        client.cookies['session_id'] = 'not-a-uuid'
        resp = await client.get(ME_PATH)
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_excludes_prohibited_fields(
        self, client: AsyncClient, app: object
    ) -> None:
        """NFR-004: login response excludes prohibited fields."""
        email = await _signup(client, app)
        resp = await _login(client, email)
        data = resp.json()
        user_keys = set(data.get('user', {}).keys())
        excluded = {'password_hash', 'csrf_token_hash', 'ip_address'}
        assert user_keys.isdisjoint(excluded)
        assert 'session_id' not in data
        assert 'user_agent' not in data.get('session', {})


class TestRememberMeLifetimes:
    """FR-004/FR-005: remember_me selects the absolute lifetime."""

    @pytest.mark.asyncio
    async def test_default_login_lifetimes(
        self, client: AsyncClient, app: object
    ) -> None:
        email = await _signup(client, app)
        with freeze_time('2026-02-01 10:00:00'):
            resp = await _login(client, email)
        assert resp.status_code == 200
        meta = resp.json()['session']
        idle = datetime.fromisoformat(meta['expires_at'])
        absolute = datetime.fromisoformat(meta['absolute_expires_at'])
        base = datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc)
        assert abs((idle - base).total_seconds() - 30 * 60) < 2
        assert abs((absolute - base).total_seconds() - 8 * 3600) < 2

    @pytest.mark.asyncio
    async def test_remember_me_extends_absolute_only(
        self, client: AsyncClient, app: object
    ) -> None:
        email = await _signup(client, app)
        with freeze_time('2026-02-01 10:00:00'):
            resp = await _login(client, email, remember_me=True)
        assert resp.status_code == 200
        meta = resp.json()['session']
        idle = datetime.fromisoformat(meta['expires_at'])
        absolute = datetime.fromisoformat(meta['absolute_expires_at'])
        base = datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc)
        # Idle window stays 30 min; absolute extends to 30 days.
        assert abs((idle - base).total_seconds() - 30 * 60) < 2
        assert abs((absolute - base).total_seconds() - 30 * 86400) < 2


class TestAccountStateGuard:
    """FR-002: non-ACTIVE accounts get structured 403 responses."""

    @pytest.mark.asyncio
    async def test_pending_account_403(
        self, client: AsyncClient, app: object
    ) -> None:
        email = await _signup(client, app, verify=False)
        resp = await _login(client, email)
        assert resp.status_code == 403
        assert resp.json()['error_code'] == 'email_not_verified'

    @pytest.mark.asyncio
    async def test_suspended_account_403(
        self,
        client: AsyncClient,
        app: object,
        db_session_maker: T_Maker,
    ) -> None:
        email = await _signup(client, app)
        await _set_status(db_session_maker, email, UserStatus.SUSPENDED)
        resp = await _login(client, email)
        assert resp.status_code == 403
        assert resp.json()['error_code'] == 'account_suspended'

    @pytest.mark.asyncio
    async def test_banned_account_403(
        self,
        client: AsyncClient,
        app: object,
        db_session_maker: T_Maker,
    ) -> None:
        email = await _signup(client, app)
        await _set_status(db_session_maker, email, UserStatus.BANNED)
        resp = await _login(client, email)
        assert resp.status_code == 403
        assert resp.json()['error_code'] == 'account_banned'


class TestPerAccountLockout:
    """FR-006: per-account sliding-window failures trigger lockout."""

    @pytest.mark.asyncio
    async def test_lockout_lifecycle(
        self, client: AsyncClient, app: object
    ) -> None:
        """5 failures -> 429 on the 6th attempt -> success after 31 min.

        Semantics per design §16 (``LOGIN_PER_ACCOUNT_MAX_ATTEMPTS = 5
        # 6th triggers lockout``) and the limiter unit tests: five
        recorded failures, the sixth attempt is rejected. NOTE: the
        tasks.md checklist phrases this as "6 failures -> 429 on 7th";
        that wording conflicts with the approved design comment.
        """
        email = await _signup(client, app)
        ip = _unique_ip()
        with freeze_time('2026-03-01 12:00:00') as frozen:
            for _ in range(5):
                resp = await _login(client, email, WRONG_PASSWORD, ip=ip)
                assert resp.status_code == 401
            locked = await _login(client, email, WRONG_PASSWORD, ip=ip)
            assert locked.status_code == 429
            assert locked.json()['error_code'] == 'rate_limited'
            # Even the correct password is rejected while locked.
            still = await _login(client, email, PASSWORD, ip=ip)
            assert still.status_code == 429
            frozen.move_to(datetime(2026, 3, 1, 12, 31, tzinfo=timezone.utc))
            ok = await _login(client, email, PASSWORD, ip=ip)
            assert ok.status_code == 200


class TestPerIpThrottle:
    """FR-007: per-IP sliding window over ALL login attempts."""

    @pytest.mark.asyncio
    async def test_21st_attempt_from_ip_rejected(
        self,
        client: AsyncClient,
        app: object,
        real_login_limiter: LoginRateLimiter,
    ) -> None:
        """Boundary wiring: a full IP window rejects the next attempt."""
        ip = _unique_ip()
        for i in range(20):
            await real_login_limiter.record_failure(
                f'probe{i}@example.com', ip
            )
        resp = await _login(client, 'nobody@example.com', 'x', ip=ip)
        assert resp.status_code == 429
        assert resp.json()['error_code'] == 'rate_limited'

    @pytest.mark.asyncio
    async def test_every_attempt_counts_toward_ip_window(
        self,
        client: AsyncClient,
        app: object,
        real_login_limiter: LoginRateLimiter,
    ) -> None:
        """FR-007: the per-IP counter increments on EVERY attempt.

        Two no-user HTTP attempts on top of 18 seeded attempts fill the
        20-attempt window, so the 21st attempt from the same IP is
        rejected (design §8: every attempt counts, success or failure).
        """
        ip = _unique_ip()
        # Seed 18 attempts from this IP (distinct accounts, no lockout).
        for i in range(18):
            await real_login_limiter.record_failure(f'seed{i}@example.com', ip)
        # Two no-user HTTP attempts must bring the window to 20.
        for i in range(2):
            resp = await _login(client, f'ghost{i}@example.com', 'x', ip=ip)
            assert resp.status_code == 401
        # The 21st attempt from this IP must be rejected.
        resp = await _login(client, 'ghost2@example.com', 'x', ip=ip)
        assert resp.status_code == 429
        assert resp.json()['error_code'] == 'rate_limited'


class TestConcurrentSessionCap:
    """FR-008/FR-018: the 11th active session is rejected with a hint."""

    @pytest.mark.asyncio
    async def test_11th_session_rejected_with_recovery(
        self,
        client: AsyncClient,
        app: object,
        db_session_maker: T_Maker,
    ) -> None:
        email = await _signup(client, app)
        await _seed_sessions(db_session_maker, email, 10)
        resp = await _login(client, email)
        assert resp.status_code == 429
        body = resp.json()
        assert body['error_code'] == 'too_many_active_sessions'
        assert body['recovery'] == ['logout_all']


class TestLogout:
    """FR-009: logout deactivates the session and clears both cookies."""

    @pytest.mark.asyncio
    async def test_logout_clears_session_and_cookies(
        self, client: AsyncClient, app: object
    ) -> None:
        email = await _signup(client, app)
        await _login(client, email)
        token = _csrf(client)
        resp = await client.post(LOGOUT_PATH, headers={'X-CSRF-Token': token})
        assert resp.status_code == 200
        assert resp.json()['message'] == 'Logged out'
        # FR-015: deletion repeats the original Path attributes.
        session_clear = _set_cookie_headers(resp, 'session_id')
        csrf_clear = _set_cookie_headers(resp, 'csrf_token')
        assert 'path=/api/v1/auth' in session_clear.lower()
        assert 'max-age=0' in session_clear.lower()
        assert 'path=/' in csrf_clear.lower()
        assert 'max-age=0' in csrf_clear.lower()
        # The session is invalidated: subsequent requests are 401.
        me = await client.get(ME_PATH)
        assert me.status_code == 401

    @pytest.mark.asyncio
    async def test_logout_all_revokes_current_only(
        self, client: AsyncClient, app: object
    ) -> None:
        """FR-010 edge case: only the current session -> revoked: 1."""
        email = await _signup(client, app)
        await _login(client, email)
        token = _csrf(client)
        resp = await client.post(
            LOGOUT_ALL_PATH, headers={'X-CSRF-Token': token}
        )
        assert resp.status_code == 200
        assert resp.json()['sessions_revoked'] == 1
        me = await client.get(ME_PATH)
        assert me.status_code == 401

    @pytest.mark.asyncio
    async def test_logout_all_revokes_every_session(
        self,
        client: AsyncClient,
        app: object,
        db_session_maker: T_Maker,
    ) -> None:
        """FR-010: all active sessions for the user are revoked."""
        email = await _signup(client, app)
        await _login(client, email)
        await _seed_sessions(db_session_maker, email, 2)
        token = _csrf(client)
        resp = await client.post(
            LOGOUT_ALL_PATH, headers={'X-CSRF-Token': token}
        )
        assert resp.status_code == 200
        assert resp.json()['sessions_revoked'] == 3
        me = await client.get(ME_PATH)
        assert me.status_code == 401

    @pytest.mark.asyncio
    async def test_logout_without_session_is_401(
        self, client: AsyncClient
    ) -> None:
        """Design §8: no session cookie -> 401 via get_current_user."""
        resp = await client.post(LOGOUT_PATH)
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_logout_all_without_session_is_401(
        self, client: AsyncClient
    ) -> None:
        """Design §8: no session cookie -> 401 via get_current_user."""
        resp = await client.post(LOGOUT_ALL_PATH)
        assert resp.status_code == 401


class TestCsrfEnforcement:
    """FR-011: double-submit + synchronizer checks at the middleware."""

    @pytest.mark.asyncio
    async def test_missing_header_is_403(
        self, client: AsyncClient, app: object
    ) -> None:
        email = await _signup(client, app)
        await _login(client, email)
        resp = await client.post(LOGOUT_PATH)
        assert resp.status_code == 403
        assert resp.json()['error_code'] == 'csrf_token_missing'

    @pytest.mark.asyncio
    async def test_mismatched_header_is_403(
        self, client: AsyncClient, app: object
    ) -> None:
        email = await _signup(client, app)
        await _login(client, email)
        resp = await client.post(
            LOGOUT_PATH, headers={'X-CSRF-Token': 'bogus-token'}
        )
        assert resp.status_code == 403
        assert resp.json()['error_code'] == 'csrf_token_mismatch'

    @pytest.mark.asyncio
    async def test_forged_double_submit_is_403(
        self, client: AsyncClient, app: object
    ) -> None:
        """A bare double-submit pair not bound to the session fails."""
        email = await _signup(client, app)
        await _login(client, email)
        forged = secrets.token_urlsafe(32)
        client.cookies['csrf_token'] = forged
        resp = await client.post(LOGOUT_PATH, headers={'X-CSRF-Token': forged})
        assert resp.status_code == 403
        assert resp.json()['error_code'] == 'csrf_token_mismatch'

    @pytest.mark.asyncio
    async def test_valid_header_passes(
        self, client: AsyncClient, app: object
    ) -> None:
        email = await _signup(client, app)
        await _login(client, email)
        resp = await client.post(
            LOGOUT_PATH, headers={'X-CSRF-Token': _csrf(client)}
        )
        assert resp.status_code == 200


class TestMe:
    """GET /me: re-echo contract and FR-012 non-rotation."""

    @pytest.mark.asyncio
    async def test_me_echoes_user_and_csrf(
        self, client: AsyncClient, app: object
    ) -> None:
        email = await _signup(client, app)
        login = await _login(client, email)
        token = login.json()['csrf_token']
        resp = await client.get(ME_PATH)
        assert resp.status_code == 200
        data = resp.json()
        assert data['user']['email'] == email
        assert data['user']['user_status'] == 'active'
        assert data['csrf_token'] == token

    @pytest.mark.asyncio
    async def test_activity_does_not_rotate_csrf(
        self, client: AsyncClient, app: object
    ) -> None:
        email = await _signup(client, app)
        login = await _login(client, email)
        token = login.json()['csrf_token']
        first = await client.get(ME_PATH)
        second = await client.get(ME_PATH)
        assert first.json()['csrf_token'] == token
        assert second.json()['csrf_token'] == token

    @pytest.mark.asyncio
    async def test_each_login_mints_a_new_csrf(
        self, client: AsyncClient, app: object
    ) -> None:
        email = await _signup(client, app)
        first = await _login(client, email)
        second = await _login(client, email)
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()['csrf_token'] != second.json()['csrf_token']


class TestSessionLifecycle:
    """FR-005: idle and absolute expiry at the HTTP boundary."""

    @pytest.mark.asyncio
    async def test_idle_expiry_deactivates_session(
        self,
        client: AsyncClient,
        app: object,
        db_session_maker: T_Maker,
    ) -> None:
        email = await _signup(client, app)
        with freeze_time('2026-04-01 09:00:00') as frozen:
            await _login(client, email)
            session_id = UUID(client.cookies['session_id'])
            frozen.move_to(datetime(2026, 4, 1, 9, 31, tzinfo=timezone.utc))
            resp = await client.get(ME_PATH)
            assert resp.status_code == 401
        row = await _get_session_row(db_session_maker, session_id)
        assert row.is_active is False

    @pytest.mark.asyncio
    async def test_idle_window_resets_on_activity(
        self, client: AsyncClient, app: object
    ) -> None:
        """FR-005: activity resets the idle window to request time + 30m.

        The idle window slides on every authenticated request: after
        activity at 09:45 the session stays valid until 10:15, and the
        request at 10:16 is rejected as idle-expired.
        """
        email = await _signup(client, app)
        with freeze_time('2026-04-01 09:00:00') as frozen:
            await _login(client, email)
            # Activity at +20 min: idle window slides to 09:50.
            frozen.move_to(datetime(2026, 4, 1, 9, 20, tzinfo=timezone.utc))
            assert (await client.get(ME_PATH)).status_code == 200
            # 09:45 is 25 min after the last activity: still valid, and
            # slides the window to 10:15.
            frozen.move_to(datetime(2026, 4, 1, 9, 45, tzinfo=timezone.utc))
            assert (await client.get(ME_PATH)).status_code == 200
            # 10:16 is 31 min after the 09:45 activity: expired.
            frozen.move_to(datetime(2026, 4, 1, 10, 16, tzinfo=timezone.utc))
            assert (await client.get(ME_PATH)).status_code == 401

    @pytest.mark.asyncio
    async def test_absolute_expiry_deactivates_session(
        self,
        client: AsyncClient,
        app: object,
        db_session_maker: T_Maker,
    ) -> None:
        email = await _signup(client, app)
        with freeze_time('2026-04-01 09:00:00') as frozen:
            await _login(client, email)
            session_id = UUID(client.cookies['session_id'])
            frozen.move_to(datetime(2026, 4, 1, 17, 1, tzinfo=timezone.utc))
            resp = await client.get(ME_PATH)
            assert resp.status_code == 401
        row = await _get_session_row(db_session_maker, session_id)
        assert row.is_active is False


class TestCookieContract:
    """FR-015: cookie attribute contract on login and logout."""

    @pytest.mark.asyncio
    async def test_login_sets_cookie_attributes(
        self, client: AsyncClient, app: object
    ) -> None:
        email = await _signup(client, app)
        resp = await _login(client, email)
        session_h = _set_cookie_headers(resp, 'session_id').lower()
        csrf_h = _set_cookie_headers(resp, 'csrf_token').lower()
        assert 'httponly' in session_h
        assert 'secure' in session_h
        assert 'samesite=lax' in session_h
        assert 'path=/api/v1/auth' in session_h
        assert 'httponly' not in csrf_h
        assert 'secure' in csrf_h
        assert 'samesite=lax' in csrf_h
        assert 'path=/' in csrf_h


class TestEmailNormalization:
    """FR-014: EmailStr normalization + exact-string lookup."""

    @pytest.mark.asyncio
    async def test_domain_case_variant_matches(
        self, client: AsyncClient, app: object
    ) -> None:
        """EmailStr lowercases the domain on both signup and login."""
        email = await _signup(
            client, app, local_part='Fr14Case', domain='Example.COM'
        )
        local, _, _domain = email.partition('@')
        resp = await _login(client, f'{local}@EXAMPLE.com')
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_local_part_case_is_exact(
        self, client: AsyncClient, app: object
    ) -> None:
        """The local part is preserved: case variants are distinct."""
        email = await _signup(client, app, local_part='Fr14Local')
        lowered = f'fr14local_{email.split("_", 1)[1]}'
        resp = await _login(client, lowered)
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_plus_tag_is_exact_identity(
        self, client: AsyncClient, app: object
    ) -> None:
        email = await _signup(client, app, local_part='tagged+plus')
        ok = await _login(client, email)
        assert ok.status_code == 200
        untagged = email.replace('tagged+plus_', 'tagged_')
        resp = await _login(client, untagged)
        assert resp.status_code == 401


class TestPiiFreeLogging:
    """FR-016/NFR-005: no PII at INFO+ on the auth boundary."""

    @pytest.mark.asyncio
    async def test_auth_boundary_logs_contain_no_pii(
        self,
        client: AsyncClient,
        app: object,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        email = await _signup(client, app)
        with caplog.at_level(logging.INFO, logger='questr.auth'):
            await _login(client, email)
            await _login(client, email, WRONG_PASSWORD)
            session_id = client.cookies['session_id']
            token = _csrf(client)
            await client.post(LOGOUT_PATH, headers={'X-CSRF-Token': token})
        records = [r for r in caplog.records if r.name == 'questr.auth']
        assert records, 'auth boundary produced no logs at INFO'
        blob = '\n'.join(f'{r.getMessage()} {r.__dict__}' for r in records)
        assert email not in blob
        assert PASSWORD not in blob
        assert WRONG_PASSWORD not in blob
        assert token not in blob
        assert session_id not in blob


class TestStaleCookie:
    """Stale-cookie regression: exempt routes keep working."""

    @pytest.mark.asyncio
    async def test_exempt_routes_work_with_stale_session_cookie(
        self,
        client: AsyncClient,
        app: object,
        db_session_maker: T_Maker,
    ) -> None:
        email = await _signup(client, app)
        await _login(client, email)
        stale_sid = client.cookies['session_id']
        stale_csrf = client.cookies['csrf_token']
        # Invalidate the session server-side.
        async with db_session_maker() as session:
            await SessionRepository(session).deactivate(UUID(stale_sid))
            await session.commit()
        # Re-login succeeds (login is on the middleware allowlist).
        again = await _login(client, email)
        assert again.status_code == 200
        # /me with the stale cookie is a clean 401, never a 500/403.
        client.cookies['session_id'] = stale_sid
        client.cookies['csrf_token'] = stale_csrf
        assert (await client.get(ME_PATH)).status_code == 401
        # Signup and resend-verification are unaffected by stale cookies.
        other = await _signup(client, app, local_part='stale_other')
        assert other
        resend = await client.post(
            '/api/v1/auth/resend-verification',
            json={'email': other},
        )
        assert resend.status_code == 200


class TestTimingEqualization:
    """FR-017: failure branches must be timing-indistinguishable.

    No freezegun here: it patches ``time.monotonic``/``perf_counter``
    and would collapse all measured durations, while Argon2 keeps
    burning real CPU time (design §15).
    """

    @staticmethod
    async def _timed(coro: Coroutine[Any, Any, object]) -> float:
        start = time.perf_counter()
        await coro
        return time.perf_counter() - start

    @pytest.mark.asyncio
    async def test_failure_branches_are_indistinguishable(
        self, client: AsyncClient, app: object
    ) -> None:
        verified = await _signup(client, app, local_part='timing_ok')
        pending = await _signup(
            client, app, verify=False, local_part='timing_pending'
        )
        ip = _unique_ip()
        samples: dict[str, list[float]] = {
            'no_user': [],
            'wrong_password': [],
            'wrong_status': [],
        }
        for i in range(5):
            samples['no_user'].append(
                await self._timed(
                    _login(client, f'ghost{i}@example.com', 'x', ip=ip)
                )
            )
            samples['wrong_password'].append(
                await self._timed(
                    _login(client, verified, WRONG_PASSWORD, ip=ip)
                )
            )
            samples['wrong_status'].append(
                await self._timed(_login(client, pending, 'x', ip=ip))
            )
        medians = {k: statistics.median(v) for k, v in samples.items()}
        # Generous tolerance band per design §15 (absorbs CI jitter).
        ratio = max(medians.values()) / min(medians.values())
        assert ratio < 1.5, f'branch medians diverge: {medians}'

    @pytest.mark.asyncio
    async def test_locked_branch_stays_fast(
        self,
        client: AsyncClient,
        app: object,
        real_login_limiter: LoginRateLimiter,
    ) -> None:
        """TD-006: the 429 branch must NOT burn Argon2 CPU time."""
        email = await _signup(client, app)
        ip = _unique_ip()
        for _ in range(5):
            await real_login_limiter.record_failure(email, ip)
        elapsed = await self._timed(_login(client, email, PASSWORD, ip=ip))
        assert elapsed < 0.5, f'locked branch took {elapsed:.3f}s'


class TestPerformanceBenchmarks:
    """NFR-002 gates (TD-002 residual-risk benchmarks)."""

    @staticmethod
    def _p95(samples: list[float]) -> float:
        ordered = sorted(samples)
        index = min(len(ordered) - 1, int(len(ordered) * 0.95 + 0.999))
        return ordered[index]

    @pytest.mark.asyncio
    async def test_authenticated_path_p95_under_50ms(
        self, client: AsyncClient, app: object
    ) -> None:
        """Session lookup + ``update_last_activity`` write per request.

        ``GET /me`` covers two of the three benchmark operations; the
        CSRF middleware adds one more indexed read on state-changing
        routes only (design §15).
        """
        email = await _signup(client, app)
        await _login(client, email)
        # Warm-up: connection pool and prepared statements.
        for _ in range(2):
            await client.get(ME_PATH)
        samples = []
        for _ in range(20):
            start = time.perf_counter()
            resp = await client.get(ME_PATH)
            samples.append(time.perf_counter() - start)
            assert resp.status_code == 200
        p95 = self._p95(samples)
        assert p95 < 0.050, f'authenticated-path p95 {p95 * 1000:.1f}ms'

    @pytest.mark.asyncio
    async def test_login_p95_under_250ms_excluding_verify(
        self, client: AsyncClient, app: object
    ) -> None:
        """Login endpoint p95 minus the measured Argon2 verify cost."""
        email = await _signup(client, app)
        hashed = hash_password(PASSWORD)
        start = time.perf_counter()
        verify_password(PASSWORD, hashed)
        verify_cost = time.perf_counter() - start
        samples = []
        for _ in range(8):
            start = time.perf_counter()
            resp = await _login(client, email)
            samples.append(time.perf_counter() - start)
            assert resp.status_code == 200
        adjusted = self._p95(samples) - verify_cost
        assert adjusted < 0.250, (
            f'login p95 excluding verify: {adjusted * 1000:.1f}ms'
        )
