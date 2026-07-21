from __future__ import annotations

import time
import uuid

from redis.asyncio import Redis

from questr.common.exceptions import (
    RateLimiterUnavailableError,
    RateLimitExceededError,
)
from questr.infrastructure.redis import get_redis
from questr.settings import settings


async def get_login_rate_limiter() -> 'LoginRateLimiter':
    """Factory for LoginRateLimiter wired from settings."""
    redis = get_redis()
    return LoginRateLimiter(
        redis=redis,
        per_account_max_attempts=settings.LOGIN_PER_ACCOUNT_MAX_ATTEMPTS,
        per_account_window_minutes=settings.LOGIN_PER_ACCOUNT_WINDOW_MINUTES,
        lockout_minutes=settings.LOGIN_LOCKOUT_MINUTES,
        per_ip_max_attempts=settings.LOGIN_PER_IP_MAX_ATTEMPTS,
        per_ip_window_minutes=settings.LOGIN_PER_IP_WINDOW_MINUTES,
    )


class LoginRateLimiter:
    """Redis-backed rate limiter with per-account lockout + per-IP throttle.

    Per-account: sliding window of failure timestamps in a sorted set.
    When the failure count reaches ``per_account_max_attempts`` a lockout
    trigger marker is written and the account stays locked for
    ``lockout_minutes`` from that trigger (FR-006).

    Per-IP: sliding window of ALL attempt timestamps. When the count exceeds
    ``per_ip_max_attempts``, further attempts from that IP are rejected.

    Fail-closed: all Redis operations are wrapped so that ``ConnectionError``
    and ``TimeoutError`` raise ``RateLimiterUnavailableError``.
    """

    def __init__(  # noqa: PLR0913, PLR0917
        self,
        redis: Redis,
        per_account_max_attempts: int = 5,
        per_account_window_minutes: int = 15,
        lockout_minutes: int = 30,
        per_ip_max_attempts: int = 20,
        per_ip_window_minutes: int = 10,
    ) -> None:
        self.redis = redis
        self.per_account_max_attempts = per_account_max_attempts
        self.per_account_window_seconds = per_account_window_minutes * 60
        self.lockout_seconds = lockout_minutes * 60
        self.per_ip_max_attempts = per_ip_max_attempts
        self.per_ip_window_seconds = per_ip_window_minutes * 60

    def _account_key(self, account_key: str) -> str:
        return f'login:account:{account_key}'

    def _ip_key(self, ip_key: str) -> str:
        return f'login:ip:{ip_key}'

    def _lockout_key(self, account_key: str) -> str:
        return f'login:lockout:{account_key}'

    async def _safe_call(
        self, method: object, *args: object, **kwargs: object
    ) -> object:
        """Call a Redis method, converting connection errors.

        Wraps both method call and await so that mocking with
        ``AsyncMock(side_effect=Exception(...))`` (raises on call,
        not only on await) is properly caught.
        """
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

    async def check_login_allowed(self, account_key: str, ip_key: str) -> None:
        """Raise if per-IP throttled or per-account locked out.

        Raises:
            RateLimitExceededError: if IP throttled or account locked.
            RateLimiterUnavailableError: if Redis is unavailable.
        """
        now = time.time()
        a_key = self._account_key(account_key)
        i_key = self._ip_key(ip_key)

        # --- Per-IP throttle check ---
        # Clean entries older than the IP window, then count
        ip_window_start = now - self.per_ip_window_seconds
        await self._safe_call(
            self.redis.zremrangebyscore, i_key, 0, ip_window_start
        )
        ip_count = await self._safe_call(self.redis.zcard, i_key)
        if ip_count is not None and ip_count >= self.per_ip_max_attempts:
            raise RateLimitExceededError('Too many attempts from this IP')

        # --- Per-account lockout check ---
        # The lockout is anchored to the trigger marker written by
        # record_failure() when the threshold was reached, so the lockout
        # window runs from the trigger (FR-006), not from the oldest
        # failure in the sliding window.
        l_key = self._lockout_key(account_key)
        marker = await self._safe_call(
            self.redis.zrange, l_key, 0, 0, False, True
        )
        if marker:
            trigger_time = marker[0][1]
            if now - trigger_time < self.lockout_seconds:
                raise RateLimitExceededError(
                    'Account temporarily locked. Try again later.'
                )
            # Lockout expired -- clear the marker and the failures.
            await self._safe_call(self.redis.delete, l_key)
            await self._safe_call(self.redis.delete, a_key)

    async def record_failure(self, account_key: str, ip_key: str) -> None:
        """Record a failed attempt in both counters.

        When the per-account in-window failure count reaches the
        threshold, a lockout trigger marker is written (NX: the first
        trigger wins, so failures recorded during an active lockout do
        not extend it).
        """
        now = time.time()
        a_key = self._account_key(account_key)
        i_key = self._ip_key(ip_key)

        # Use unique member name per call (two failures with the same
        # ``time.time()`` value would otherwise overwrite each other
        # since Redis sorted set members must be unique).
        member = f'{now}:{uuid.uuid4().hex}'
        await self._safe_call(self.redis.zadd, a_key, {member: now})
        await self._safe_call(self.redis.zadd, i_key, {member: now})

        # Count only failures inside the sliding window (FR-006).
        window_start = now - self.per_account_window_seconds
        await self._safe_call(
            self.redis.zremrangebyscore, a_key, 0, window_start
        )
        count = await self._safe_call(self.redis.zcard, a_key)
        if count is not None and count >= self.per_account_max_attempts:
            await self._safe_call(
                self.redis.zadd,
                self._lockout_key(account_key),
                {'trigger': now},
                nx=True,
            )

    async def record_success(self, account_key: str) -> None:
        """Reset the per-account failure counter on successful login."""
        await self._safe_call(
            self.redis.delete, self._account_key(account_key)
        )
        await self._safe_call(
            self.redis.delete, self._lockout_key(account_key)
        )

    async def record_ip_attempt(self, ip_key: str) -> None:
        """Record an attempt in the per-IP window only (FR-007).

        Every login attempt counts toward the per-IP window, including
        attempts targeting nonexistent accounts and successful logins.
        The per-account counter is not touched.
        """
        now = time.time()
        member = f'{now}:{uuid.uuid4().hex}'
        await self._safe_call(
            self.redis.zadd, self._ip_key(ip_key), {member: now}
        )
