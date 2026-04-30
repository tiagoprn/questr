"""Shared test fixtures — session-scoped infrastructure containers."""

from collections.abc import AsyncGenerator, Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from questr.infrastructure.orm.base import Base


@pytest.fixture(scope='session')
def postgres_url() -> Generator[str, None, None]:
    with PostgresContainer('postgres:18-alpine') as postgres:
        yield postgres.get_connection_url(driver='psycopg')


@pytest.fixture(scope='session')
def redis_url() -> Generator[str, None, None]:
    with RedisContainer('redis:7-alpine') as redis:
        yield redis.get_connection_url()


@pytest_asyncio.fixture(scope='session')
async def db_engine(
    postgres_url: str,
) -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(postgres_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope='session')
async def db_session_maker(
    db_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session(
    db_session_maker: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    async with db_session_maker() as session:
        await session.begin_nested()
        yield session
        await session.rollback()


def make_mock_rate_limiter() -> Any:
    """Create a mock rate limiter that allows all requests."""
    mock = MagicMock()
    mock.is_allowed = AsyncMock(return_value=True)
    return mock
