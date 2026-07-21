"""Behavior test fixtures — FastAPI app with test DB overrides."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from questr.factory import create_app
from questr.infrastructure.login_rate_limiter import (
    LoginRateLimiter,
    get_login_rate_limiter,
)
from questr.infrastructure.orm.base import get_async_session
from questr.infrastructure.rate_limiter import get_rate_limiter
from tests.conftest import make_mock_rate_limiter


@pytest.fixture(scope='module')
def event_loop():
    """Module-scoped event loop for ASGI middleware compatibility."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope='module')
async def real_login_limiter(redis_url: str) -> LoginRateLimiter:
    """Create a real Redis-backed LoginRateLimiter for behavior tests."""
    redis = Redis.from_url(redis_url)
    yield LoginRateLimiter(redis=redis)
    await redis.flushall()
    await redis.aclose()


@pytest_asyncio.fixture
async def app(
    db_session: AsyncSession,
    real_login_limiter: LoginRateLimiter,
) -> FastAPI:
    application = create_app()

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    async def override_get_rate_limiter() -> Any:
        return make_mock_rate_limiter()

    async def override_get_login_limiter() -> LoginRateLimiter:
        return real_login_limiter

    application.dependency_overrides[get_async_session] = override_get_session
    application.dependency_overrides[get_rate_limiter] = (
        override_get_rate_limiter
    )
    application.dependency_overrides[get_login_rate_limiter] = (
        override_get_login_limiter
    )
    return application


@pytest_asyncio.fixture
async def client(
    app: FastAPI,
) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url='http://test',
    ) as ac:
        yield ac
