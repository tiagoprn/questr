"""Behavior test fixtures — FastAPI app with test DB overrides."""

from collections.abc import AsyncGenerator
from typing import Any

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from questr.factory import create_app
from questr.infrastructure.orm.base import get_async_session
from questr.infrastructure.rate_limiter import get_rate_limiter
from tests.conftest import make_mock_rate_limiter


@pytest_asyncio.fixture
async def app(
    db_session: AsyncSession,
) -> FastAPI:
    application = create_app()

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    async def override_get_rate_limiter() -> Any:
        return make_mock_rate_limiter()

    application.dependency_overrides[get_async_session] = override_get_session
    application.dependency_overrides[get_rate_limiter] = (
        override_get_rate_limiter
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
