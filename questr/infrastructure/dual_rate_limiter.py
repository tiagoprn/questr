"""Fail-closed dual rate limiter for credential-recovery email sends.

Counts per-account AND per-IP in sliding windows, but only consumes a
slot when an email is actually enqueued (two-phase check-then-consume).
Per-account is more generous than per-IP so a single account can retry
a few times while a single IP cannot spam many accounts.
"""

import time
from uuid import uuid4

from redis.asyncio import Redis

from questr.common.exceptions import (
    RateLimiterUnavailableError,
    RateLimitExceededError,
)
from questr.infrastructure.redis import get_redis
from questr.settings import settings


async def get_dual_rate_limiter() -> 'DualRateLimiter':
    """Factory for DualRateLimiter wired from settings.

    Per-account is more generous than per-IP: the per-IP cap is derived
    as a fraction of the per-account cap so a single IP cannot spam many
    accounts while a legitimate account can retry a few times.
    """
    redis = get_redis()
    per_account_max = settings.RATE_LIMIT_FORGOT_MAX
    return DualRateLimiter(
        redis=redis,
        per_account_max=per_account_max,
        per_ip_max=max(1, per_account_max // 2),
        window_seconds=settings.RATE_LIMIT_FORGOT_WINDOW_HOURS * 3600,
    )


async def get_dual_rate_limiter_email_change() -> 'DualRateLimiter':
    """Factory for the change-email DualRateLimiter.

    Wired from the ``RATE_LIMIT_EMAIL_CHANGE_*`` settings and namespaced
    under its own Redis keys so it is independent of the forgot-password
    limiter (gate 6): a change-email burst cannot deplete the
    forgot-password budget and vice versa.
    """
    redis = get_redis()
    per_account_max = settings.RATE_LIMIT_EMAIL_CHANGE_MAX
    return DualRateLimiter(
        redis=redis,
        per_account_max=per_account_max,
        per_ip_max=max(1, per_account_max // 2),
        window_seconds=settings.RATE_LIMIT_EMAIL_CHANGE_WINDOW_HOURS * 3600,
        key_prefix='email_change',
    )


class DualRateLimiter:
    """Redis-backed per-account + per-IP limiter with count-on-send.

    ``check_allowed`` inspects both windows without consuming; the
    caller performs the work and calls ``consume_on_send`` only when an
    email is enqueued, so failed or no-op branches never count.

    Fail-closed: all Redis operations are wrapped so that connection
    errors raise ``RateLimiterUnavailableError``.
    """

    def __init__(
        self,
        redis: Redis,
        per_account_max: int,
        per_ip_max: int,
        window_seconds: int,
        key_prefix: str = 'dual',
    ) -> None:
        self.redis = redis
        self.per_account_max = per_account_max
        self.per_ip_max = per_ip_max
        self.window_seconds = window_seconds
        self.key_prefix = key_prefix

    def _account_key(self, account_key: str) -> str:
        return f'{self.key_prefix}:account:{account_key}'

    def _ip_key(self, ip_key: str) -> str:
        return f'{self.key_prefix}:ip:{ip_key}'

    async def _safe_call(
        self, method: object, *args: object, **kwargs: object
    ) -> object:
        """Call a Redis method, converting connection errors."""
        try:
            coro = method(*args, **kwargs)  # type: ignore[operator]
        except (ConnectionError, TimeoutError, OSError) as exc:
            raise RateLimiterUnavailableError(
                'Rate limiter unavailable'
            ) from exc
        try:
            return await coro
        except (ConnectionError, TimeoutError, OSError) as exc:
            raise RateLimiterUnavailableError(
                'Rate limiter unavailable'
            ) from exc

    async def check_allowed(self, account_key: str, ip_key: str) -> None:
        """Raise if either the per-IP or per-account window is full.

        Does not consume a slot.
        """
        now = time.time()
        window_start = now - self.window_seconds

        ip_count = await self._count_window(self._ip_key(ip_key), window_start)
        if ip_count is not None and ip_count >= self.per_ip_max:
            raise RateLimitExceededError('Too many requests from this IP')

        account_count = await self._count_window(
            self._account_key(account_key), window_start
        )
        if account_count is not None and account_count >= self.per_account_max:
            raise RateLimitExceededError(
                'Too many requests for this account. Try again later.'
            )

    async def consume_on_send(self, account_key: str, ip_key: str) -> None:
        """Count a send in both windows (call only when email enqueued)."""
        now = time.time()
        member = f'{now}:{uuid4().hex}'
        a_key = self._account_key(account_key)
        i_key = self._ip_key(ip_key)

        await self._safe_call(self.redis.zadd, a_key, {member: now})
        await self._safe_call(self.redis.zadd, i_key, {member: now})
        await self._safe_call(self.redis.expire, a_key, self.window_seconds)
        await self._safe_call(self.redis.expire, i_key, self.window_seconds)

    async def _count_window(self, key: str, window_start: float) -> int | None:
        await self._safe_call(
            self.redis.zremrangebyscore, key, 0, window_start
        )
        count = await self._safe_call(self.redis.zcard, key)
        return int(count) if count is not None else None
