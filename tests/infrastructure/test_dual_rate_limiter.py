from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from redis.asyncio import Redis

from questr.common.exceptions import (
    RateLimiterUnavailableError,
    RateLimitExceededError,
)
from questr.infrastructure.dual_rate_limiter import DualRateLimiter


@pytest_asyncio.fixture
async def redis_client(redis_url: str) -> Redis:
    """Create a Redis client from the testcontainer URL."""
    r = Redis.from_url(redis_url)
    yield r
    await r.flushall()
    await r.aclose()


@pytest.fixture
def limiter(redis_client: Redis) -> DualRateLimiter:
    """Create a DualRateLimiter with per-account more generous than per-IP."""
    return DualRateLimiter(
        redis=redis_client,
        per_account_max=3,
        per_ip_max=2,
        window_seconds=3600,
    )


ACCOUNT_KEY = 'user:test-user-id'
IP_KEY = 'ip:127.0.0.1'


class TestDualRateLimiter:
    """Tests for DualRateLimiter check-then-consume semantics."""

    async def test_check_allowed_passes_under_limits(
        self, limiter: DualRateLimiter
    ) -> None:
        await limiter.check_allowed(ACCOUNT_KEY, IP_KEY)

    async def test_consume_on_send_counts_toward_per_ip(
        self, limiter: DualRateLimiter
    ) -> None:
        # per-IP max is 2; the 3rd send from the same IP is rejected.
        await limiter.consume_on_send(ACCOUNT_KEY, IP_KEY)
        await limiter.consume_on_send(ACCOUNT_KEY, IP_KEY)
        with pytest.raises(RateLimitExceededError):
            await limiter.check_allowed(ACCOUNT_KEY, IP_KEY)

    async def test_consume_on_send_counts_toward_per_account(
        self, limiter: DualRateLimiter
    ) -> None:
        # per-account max is 3; the 4th send for the account is rejected.
        for _ in range(3):
            await limiter.consume_on_send(ACCOUNT_KEY, IP_KEY)
        with pytest.raises(RateLimitExceededError):
            await limiter.check_allowed(ACCOUNT_KEY, IP_KEY)

    async def test_check_allowed_does_not_consume(
        self, limiter: DualRateLimiter
    ) -> None:
        # Repeated checks without sends never trip the limit.
        for _ in range(10):
            await limiter.check_allowed(ACCOUNT_KEY, IP_KEY)

    async def test_fail_closed_on_redis_down(
        self, redis_client: Redis
    ) -> None:
        broken = DualRateLimiter(
            redis=AsyncMock(
                zremrangebyscore=AsyncMock(side_effect=ConnectionError('down'))
            ),
            per_account_max=3,
            per_ip_max=2,
            window_seconds=3600,
        )
        with pytest.raises(RateLimiterUnavailableError):
            await broken.check_allowed(ACCOUNT_KEY, IP_KEY)

    async def test_independent_key_prefixes_do_not_share_windows(
        self, redis_client: Redis
    ) -> None:
        forgot = DualRateLimiter(
            redis=redis_client,
            per_account_max=1,
            per_ip_max=1,
            window_seconds=3600,
            key_prefix='forgot',
        )
        email_change = DualRateLimiter(
            redis=redis_client,
            per_account_max=1,
            per_ip_max=1,
            window_seconds=3600,
            key_prefix='email_change',
        )
        await forgot.consume_on_send(ACCOUNT_KEY, IP_KEY)
        with pytest.raises(RateLimitExceededError):
            await forgot.check_allowed(ACCOUNT_KEY, IP_KEY)
        await email_change.check_allowed(ACCOUNT_KEY, IP_KEY)
        await email_change.consume_on_send(ACCOUNT_KEY, IP_KEY)
        with pytest.raises(RateLimitExceededError):
            await email_change.check_allowed(ACCOUNT_KEY, IP_KEY)
