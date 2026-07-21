"""Behavior test fixtures — FastAPI app with committed test DB state.

Unlike the domain-layer tests (nested-transaction rollback), behavior
tests COMMIT via per-request sessions, mirroring the production
``get_async_session`` dependency: the ``CsrfMiddleware`` opens its own
connection (patched below to the testcontainers engine) and can only
see committed rows. Isolation between tests is restored by truncating
the auth tables and flushing the testcontainers Redis after each test.

The client base URL uses ``https://`` so the browser-like httpx cookie
jar returns ``Secure`` cookies on subsequent requests.
"""

from collections.abc import AsyncGenerator
from typing import Any

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

import questr.app.middleware as csrf_middleware
from questr.factory import create_app
from questr.infrastructure.login_rate_limiter import (
    LoginRateLimiter,
    get_login_rate_limiter,
)
from questr.infrastructure.orm.base import get_async_session
from questr.infrastructure.rate_limiter import get_rate_limiter
from tests.conftest import make_mock_rate_limiter


@pytest_asyncio.fixture(scope='module')
async def real_login_limiter(redis_url: str) -> LoginRateLimiter:
    """Create a real Redis-backed LoginRateLimiter for behavior tests."""
    redis = Redis.from_url(redis_url)
    yield LoginRateLimiter(redis=redis)
    await redis.flushall()
    await redis.aclose()


@pytest_asyncio.fixture(scope='module', autouse=True)
async def _patch_middleware_sessionmaker(
    db_session_maker: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[None, None]:
    """Point CsrfMiddleware's private sessionmaker at testcontainers.

    FastAPI DI is unavailable inside middleware, so ``CsrfMiddleware``
    references the module-level ``AsyncSessionLocal`` bound to the dev
    database. Behavior tests rebind that name to the session-scoped
    testcontainers sessionmaker so middleware session lookups hit the
    same database as the application routes.
    """
    original = csrf_middleware.AsyncSessionLocal
    csrf_middleware.AsyncSessionLocal = db_session_maker
    yield
    csrf_middleware.AsyncSessionLocal = original


@pytest_asyncio.fixture(autouse=True)
async def _clean_state(
    db_engine: AsyncEngine,
    real_login_limiter: LoginRateLimiter,
) -> AsyncGenerator[None, None]:
    """Reset committed DB rows and throttle state between tests."""
    yield
    async with db_engine.begin() as conn:
        await conn.execute(
            text('TRUNCATE sessions, email_verifications, users CASCADE')
        )
    await real_login_limiter.redis.flushall()


@pytest_asyncio.fixture
async def app(
    db_session_maker: async_sessionmaker[AsyncSession],
    real_login_limiter: LoginRateLimiter,
) -> FastAPI:
    application = create_app()

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        # Mirror production get_async_session: one committed session per
        # request so middleware lookups see rows written by earlier
        # requests (e.g. the session created by POST /login).
        async with db_session_maker() as session:
            yield session
            await session.commit()

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
        base_url='https://test',
    ) as ac:
        yield ac
