import asyncio
from collections.abc import AsyncGenerator, Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from questr.factory import create_app
from questr.orm.base import Base, get_async_session
from questr.users.dependencies import get_rate_limiter


@pytest.fixture(scope='session')
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope='session')
def postgres_container() -> Generator[str, None, None]:
    with PostgresContainer('postgres:18-alpine') as postgres:
        url = postgres.get_connection_url(driver=None)
        yield f'postgresql+psycopg://{url.split("://")[1]}'


@pytest.fixture(scope='session')
def redis_url() -> Generator[str, None, None]:
    with RedisContainer('redis:7-alpine') as redis:
        yield redis.get_connection_url()


@pytest_asyncio.fixture(scope='session')
async def db_engine(
    postgres_container: str,
) -> AsyncGenerator[Any, None]:
    engine = create_async_engine(postgres_container, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope='session')
async def db_session_maker(
    db_engine: Any,
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


def _make_mock_rate_limiter() -> Any:
    mock = MagicMock()
    mock.is_allowed = AsyncMock(return_value=True)
    return mock


@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession,
) -> AsyncGenerator[AsyncClient, None]:
    app = create_app()

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    async def override_get_rate_limiter() -> Any:
        return _make_mock_rate_limiter()

    app.dependency_overrides[get_async_session] = override_get_session
    app.dependency_overrides[get_rate_limiter] = override_get_rate_limiter

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url='http://test',
    ) as ac:
        yield ac
