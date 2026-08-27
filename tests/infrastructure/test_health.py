"""Unit tests for the health check functions.

The checks run against a live PostgreSQL and Redis from testcontainers. A
module-scoped fixture rebinds ``questr.infrastructure.orm.base.engine`` and
``questr.infrastructure.redis._pool`` to the test containers, because the
health module reads them lazily via module attributes (never name-bound at
import time). Components are restored in teardown.
"""

import asyncio
import json

import pytest_asyncio
from redis.asyncio import ConnectionPool
from sqlalchemy.ext.asyncio import create_async_engine

import questr.infrastructure.orm.base as orm_base
import questr.infrastructure.redis as redis_infra
from questr.infrastructure import health


@pytest_asyncio.fixture(scope='module', autouse=True)
async def _use_redirect(redirect_infrastructure) -> None:
    """Activate the shared testcontainers redirect for this module."""
    yield


async def test_check_database_healthy() -> None:
    result = await health.check_database()
    assert result['healthy'] is True


async def test_check_database_unhealthy() -> None:
    original = orm_base.engine
    # Port 1 is not listening; connection is refused immediately.
    bad = create_async_engine('postgresql+psycopg://u:p@127.0.0.1:1/db')
    orm_base.engine = bad
    try:
        result = await health.check_database()
    finally:
        orm_base.engine = original
        await bad.dispose()
    assert result['healthy'] is False
    assert result['error'] == 'database unreachable'


async def test_check_redis_healthy() -> None:
    result = await health.check_redis()
    assert result['healthy'] is True


async def test_check_redis_unhealthy() -> None:
    original = redis_infra._pool
    bad = ConnectionPool.from_url('redis://127.0.0.1:1/0')
    redis_infra._pool = bad
    try:
        result = await health.check_redis()
    finally:
        redis_infra._pool = original
        await bad.aclose()
    assert result['healthy'] is False
    assert result['error'] == 'redis unreachable'


async def test_readiness_database_timeout(monkeypatch) -> None:
    """A slow database check must normalize to an unhealthy timeout dict."""

    async def slow_database() -> None:
        await asyncio.sleep(30)

    monkeypatch.setattr(health, 'check_database', slow_database)
    monkeypatch.setattr(health.settings, 'HEALTH_CHECK_TIMEOUT_SECONDS', 0.05)
    response = await health.readiness()
    assert response.status_code == 503  # noqa: PLR2004
    body = json.loads(response.body)
    assert body['checks']['database']['healthy'] is False
    assert body['checks']['database']['error'] == 'database check timed out'
    assert body['checks']['redis']['healthy'] is True
