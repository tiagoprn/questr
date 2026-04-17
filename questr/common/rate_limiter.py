import time

from redis.asyncio import Redis


class RedisRateLimiter:
    """Rate limiter using Redis sorted sets with sliding window."""

    def __init__(
        self, redis: Redis, max_requests: int = 3, window_seconds: int = 3600
    ) -> None:
        self.redis = redis
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def is_allowed(self, key: str) -> bool:
        now = time.time()
        window_start = now - self.window_seconds
        redis_key = f'rate_limit:{key}'

        async with self.redis.pipeline(transaction=True) as pipe:
            await pipe.zremrangebyscore(redis_key, 0, window_start)
            await pipe.zadd(redis_key, {str(now): now})
            await pipe.expire(redis_key, self.window_seconds)
            await pipe.zcard(redis_key)
            results = await pipe.execute()

        request_count = results[-1]
        return request_count <= self.max_requests
