"""Behavior tests for OpenAPI docs access control."""

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from questr.factory import create_app
from questr.settings import settings


class TestDocsInDev:
    """Docs served when ENVIRONMENT=dev (default in tests)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        'path',
        ['/docs', '/redoc', '/openapi.json'],
    )
    async def test_endpoint_returns_200(
        self, client: AsyncClient, path: str
    ) -> None:
        response = await client.get(path)
        assert response.status_code == status.HTTP_200_OK


class TestDocsInProd:
    """Docs disabled when ENVIRONMENT=prod."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        'path',
        ['/docs', '/redoc', '/openapi.json'],
    )
    async def test_endpoint_returns_404(
        self, monkeypatch, path: str
    ) -> None:
        monkeypatch.setattr(settings, 'ENVIRONMENT', 'prod')
        application = create_app()

        async with AsyncClient(
            transport=ASGITransport(app=application),
            base_url='https://test',
        ) as ac:
            response = await ac.get(path)
            assert response.status_code == status.HTTP_404_NOT_FOUND
