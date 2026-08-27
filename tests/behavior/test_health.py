"""Behavior tests for the Kubernetes health endpoints.

The readiness checks run against the testcontainers PostgreSQL and Redis via
the module-scoped rebinding fixture (see the unit test notes in
``tests/infrastructure/test_health.py``).

Lifespan caveat: the ``client`` used here relies on ``httpx.ASGITransport``,
which does NOT run ASGI lifespan events, so ``app.state.started`` never
becomes ``True`` on its own. The 503 case is the default (the attribute is
absent, and the endpoint reads ``getattr(..., False)``); the 200 case sets
``app.state.started = True`` on the app fixture before the request.
"""

from collections.abc import AsyncGenerator

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from questr.factory import create_app
from questr.infrastructure.health import APP_VERSION


@pytest_asyncio.fixture(scope='module', autouse=True)
async def _use_redirect(redirect_infrastructure) -> None:
    """Activate the shared testcontainers redirect for this module."""
    yield


@pytest_asyncio.fixture
async def health_app() -> FastAPI:
    return create_app()


@pytest_asyncio.fixture
async def health_client(
    health_app: FastAPI,
) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=health_app),
        base_url='http://test',
    ) as ac:
        yield ac


async def test_liveness(health_client: AsyncClient) -> None:
    response = await health_client.get('/health')
    assert response.status_code == 200  # noqa: PLR2004
    assert response.json() == {'status': 'alive'}


async def test_started_returns_503_when_not_started(
    health_client: AsyncClient,
) -> None:
    response = await health_client.get('/health/started')
    assert response.status_code == 503  # noqa: PLR2004
    assert response.json() == {'status': 'not_started'}


async def test_started_returns_200_when_started(
    health_app: FastAPI, health_client: AsyncClient
) -> None:
    health_app.state.started = True
    response = await health_client.get('/health/started')
    assert response.status_code == 200  # noqa: PLR2004
    assert response.json() == {'status': 'started'}


async def test_readiness_returns_200_when_ready(
    health_client: AsyncClient,
) -> None:
    response = await health_client.get('/health/ready')
    assert response.status_code == 200  # noqa: PLR2004
    body = response.json()
    assert body['status'] == 'ready'
    assert body['checks']['database']['healthy'] is True
    assert body['checks']['redis']['healthy'] is True
    assert body['version'] == APP_VERSION
