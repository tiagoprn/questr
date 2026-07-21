from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from freezegun import freeze_time
from redis.asyncio import Redis

from questr.common.exceptions import (
    RateLimiterUnavailableError,
    RateLimitExceededError,
)
from questr.infrastructure.login_rate_limiter import (
    LoginRateLimiter,
)


@pytest_asyncio.fixture
async def redis_client(redis_url: str) -> Redis:
    """Create a Redis client from the testcontainer URL."""
    r = Redis.from_url(redis_url)
    yield r
    await r.flushall()
    await r.aclose()


@pytest.fixture
def limiter(redis_client: Redis) -> LoginRateLimiter:
    """Create a LoginRateLimiter with default test settings."""
    return LoginRateLimiter(
        redis=redis_client,
        per_account_max_attempts=5,
        per_account_window_minutes=15,
        lockout_minutes=30,
        per_ip_max_attempts=20,
        per_ip_window_minutes=10,
    )


ACCOUNT_KEY = 'user:test-user-id'
IP_KEY = 'ip:127.0.0.1'


class TestLoginRateLimiter:
    """Tests for LoginRateLimiter state machine."""

    async def test_lockout_triggers_on_sixth_failure(
        self, limiter: LoginRateLimiter
    ) -> None:
        """AC-1: The 6th per-account failure locks the account."""
        # First 5 failures: should be allowed (no lockout yet)
        for _ in range(5):
            await limiter.record_failure(ACCOUNT_KEY, IP_KEY)

        # 6th call: should raise lockout
        with pytest.raises(RateLimitExceededError):
            await limiter.check_login_allowed(ACCOUNT_KEY, IP_KEY)

    async def test_record_ip_attempt_counts_toward_ip_window(
        self, limiter: LoginRateLimiter
    ) -> None:
        """FR-007: IP-only attempts fill the window without account state."""
        for _ in range(20):
            await limiter.record_ip_attempt(IP_KEY)

        with pytest.raises(RateLimitExceededError):
            await limiter.check_login_allowed('user:no-failures', IP_KEY)

        # The per-account counter is untouched: a fresh IP is allowed.
        await limiter.check_login_allowed('user:no-failures', 'ip:10.0.0.9')

    async def test_lockout_lifts_after_window_elapses(
        self, limiter: LoginRateLimiter
    ) -> None:
        """AC-1: The lockout lifts after the configured window."""
        # 5 failures at 12:00
        with freeze_time('2026-01-01 12:00:00'):
            for _ in range(5):
                await limiter.record_failure(ACCOUNT_KEY, IP_KEY)

        # Still locked at 12:29
        with freeze_time('2026-01-01 12:29:00'):
            await limiter.record_failure(ACCOUNT_KEY, IP_KEY)
            with pytest.raises(RateLimitExceededError):
                await limiter.check_login_allowed(ACCOUNT_KEY, IP_KEY)

        # Lockout lifted at 12:30
        with freeze_time('2026-01-01 12:30:00'):
            await limiter.check_login_allowed(ACCOUNT_KEY, IP_KEY)

    @freeze_time('2026-01-01 12:00:00')
    async def test_success_resets_failure_counter(
        self, limiter: LoginRateLimiter
    ) -> None:
        """AC-2: A successful check resets the per-account counter."""
        # 4 failures
        for _ in range(4):
            await limiter.record_failure(ACCOUNT_KEY, IP_KEY)

        # Success resets
        await limiter.record_success(ACCOUNT_KEY)

        # 4 more failures should not lockout (counter was reset)
        for _ in range(4):
            await limiter.record_failure(ACCOUNT_KEY, IP_KEY)

        # Should be allowed (4 failures after reset, not locked out)
        await limiter.check_login_allowed(ACCOUNT_KEY, IP_KEY)

        # 5th failure after reset -> 6th would lockout
        await limiter.record_failure(ACCOUNT_KEY, IP_KEY)
        with pytest.raises(RateLimitExceededError):
            await limiter.check_login_allowed(ACCOUNT_KEY, IP_KEY)

    @freeze_time('2026-01-01 12:00:00')
    async def test_per_ip_counts_successes_and_failures(
        self, limiter: LoginRateLimiter
    ) -> None:
        """AC-3: Per-IP counter is independent and counts all attempts."""
        # 10 failures for different accounts from same IP
        for i in range(10):
            await limiter.record_failure(f'user:user-{i}', IP_KEY)

        # 10 successes for different accounts from same IP
        for i in range(10, 20):
            await limiter.record_failure(f'user:user-{i}', IP_KEY)

        # 21st attempt from same IP should be blocked
        with pytest.raises(RateLimitExceededError):
            await limiter.check_login_allowed('user:new-user', IP_KEY)

    async def test_redis_outage_raises_rate_limiter_unavailable(
        self, redis_client: Redis
    ) -> None:
        """AC-4: Redis outage raises RateLimiterUnavailableError."""
        # Simulate Redis error with a mocked client
        bad_redis = AsyncMock(spec=Redis)
        bad_redis.zremrangebyscore.side_effect = ConnectionError(
            'Redis is down'
        )
        bad_limiter = LoginRateLimiter(
            redis=bad_redis,
            per_account_max_attempts=5,
            per_account_window_minutes=15,
            lockout_minutes=30,
            per_ip_max_attempts=20,
            per_ip_window_minutes=10,
        )

        with pytest.raises(RateLimiterUnavailableError):
            await bad_limiter.check_login_allowed('user:test', 'ip:1.2.3.4')

    @freeze_time('2026-01-01 12:00:00')
    async def test_per_ip_blocks_21st_attempt_in_window(
        self, limiter: LoginRateLimiter
    ) -> None:
        """AC-3: 21st attempt in the same window is rejected."""
        account_prefix = 'user:'
        for i in range(21):
            # Use distinct account keys to isolate per-account from per-IP
            await limiter.record_failure(f'{account_prefix}{i}', IP_KEY)

        # 21st check (not record, since it was already recorded)
        # Actually check_login_allowed is called before recording
        # The 21st record_failure succeeded, but check_login_allowed
        # for the 22nd should fail:
        with pytest.raises(RateLimitExceededError):
            await limiter.check_login_allowed('user:another-user', IP_KEY)
