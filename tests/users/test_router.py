# ruff: noqa: PLR6301,PLR2004,PLR0913,PLR0917
# noqa: PLR6301,PLR2004
import pytest
from httpx import AsyncClient


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
