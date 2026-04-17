from redis.asyncio import ConnectionPool, Redis

from questr.settings import settings

_pool: ConnectionPool | None = None


def get_redis_pool() -> ConnectionPool:
    global _pool  # noqa: PLW0603
    if _pool is None:
        _pool = ConnectionPool.from_url(settings.REDIS_URL)
    return _pool


def get_redis() -> Redis:
    return Redis.from_pool(get_redis_pool())


async def close_redis() -> None:
    global _pool  # noqa: PLW0603
    if _pool is not None:
        await _pool.aclose()
        _pool = None
