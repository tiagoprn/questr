# ruff: noqa: PLR6301,PLR2004,PLR0913,PLR0917
# noqa: PLR6301,PLR2004
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from questr.common.services.email_service import (
    BaseEmailService,
    get_email_service,
)
from questr.users.dependencies import get_rate_limiter


class TestSignup:
    @pytest.mark.asyncio
    async def test_signup_returns_201(
        self,
        client: AsyncClient,
    ) -> None:
        response = await client.post(
            '/api/v1/auth/signup',
            json={
                'username': 'newuser',
                'email': 'newuser@example.com',
                'first_name': 'New',
                'last_name': 'User',
                'password': 'StrongPass1!',
                'password_confirmation': 'StrongPass1!',
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data['username'] == 'newuser'
        assert data['email'] == 'newuser@example.com'
        assert data['status'] == 'pending'

    @pytest.mark.asyncio
    async def test_signup_returns_409_on_duplicate(
        self,
        client: AsyncClient,
    ) -> None:
        payload = {
            'username': 'duplicate',
            'email': 'duplicate@example.com',
            'first_name': 'Dup',
            'last_name': 'User',
            'password': 'StrongPass1!',
            'password_confirmation': 'StrongPass1!',
        }
        await client.post('/api/v1/auth/signup', json=payload)
        response = await client.post('/api/v1/auth/signup', json=payload)
        assert response.status_code == 409


class TestVerifyEmail:
    @pytest.mark.asyncio
    async def test_verify_email_returns_400_on_invalid_token(
        self,
        client: AsyncClient,
    ) -> None:
        response = await client.post(
            '/api/v1/auth/verify-email',
            json={'token': 'invalid_token'},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_verify_email_returns_200_on_valid_token(
        self,
        app: FastAPI,
        client: AsyncClient,
    ) -> None:
        captured: dict[str, str] = {}

        class RecordingEmailService(BaseEmailService):
            async def send_verification_email(
                self, to_email: str, token: str
            ) -> bool:
                captured['token'] = token
                return True

        app.dependency_overrides[get_email_service] = (
            lambda: RecordingEmailService()
        )

        signup_response = await client.post(
            '/api/v1/auth/signup',
            json={
                'username': 'verifyme',
                'email': 'verifyme@example.com',
                'first_name': 'Verify',
                'last_name': 'Me',
                'password': 'StrongPass1!',
                'password_confirmation': 'StrongPass1!',
            },
        )
        assert signup_response.status_code == 201
        assert 'token' in captured

        verify_response = await client.post(
            '/api/v1/auth/verify-email',
            json={'token': captured['token']},
        )
        assert verify_response.status_code == 200
        assert verify_response.json()['status'] == 'active'


class TestResendVerification:
    @pytest.mark.asyncio
    async def test_resend_returns_200(
        self,
        client: AsyncClient,
    ) -> None:
        response = await client.post(
            '/api/v1/auth/resend-verification',
            json={'email': 'nonexistent@example.com'},
        )
        assert response.status_code == 200
        assert 'sent' in response.json()['message'].lower()

    @pytest.mark.asyncio
    async def test_resend_returns_429_on_rate_limit(
        self,
        app: FastAPI,
        client: AsyncClient,
    ) -> None:
        denying_limiter = MagicMock()
        denying_limiter.is_allowed = AsyncMock(return_value=False)
        app.dependency_overrides[get_rate_limiter] = (
            lambda: denying_limiter
        )

        response = await client.post(
            '/api/v1/auth/resend-verification',
            json={'email': 'someone@example.com'},
        )
        assert response.status_code == 429
