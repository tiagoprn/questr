# ruff: noqa: PLR6301,PLR2004,PLR0913,PLR0917
# noqa: PLR6301,PLR2004
import secrets

import pytest
from httpx import AsyncClient

from questr.infrastructure.email import BaseEmailService, get_email_service


async def _signup_and_verify(client: AsyncClient, app: object) -> str:
    """Signup a user, verify the email, return email used."""
    suffix = secrets.token_hex(4)
    email = f'login_test_{suffix}@example.com'
    captured: dict[str, str] = {}

    class CaptureEmail(BaseEmailService):
        async def send_verification_email(
            self, to_email: str, token: str
        ) -> bool:
            captured['token'] = token
            return True

    app.dependency_overrides[get_email_service] = CaptureEmail

    signup_resp = await client.post(
        '/api/v1/auth/signup',
        json={
            'username': f'logintest_{suffix}',
            'email': email,
            'first_name': 'Login',
            'last_name': 'Test',
            'password': 'StrongPass1!',
            'password_confirmation': 'StrongPass1!',
        },
    )
    assert signup_resp.status_code == 201
    assert 'token' in captured

    verify_resp = await client.get(
        f'/api/v1/auth/verify-email/{captured["token"]}'
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()['status'] == 'active'
    return email


class TestLoginFlow:
    """End-to-end login flow through the HTTP boundary."""

    @pytest.mark.asyncio
    async def test_happy_path_and_response_contract(
        self, client: AsyncClient, app: object
    ) -> None:
        """Happy path: signup -> verify -> login."""
        email = await _signup_and_verify(client, app)
        login_resp = await client.post(
            '/api/v1/auth/login',
            json={
                'email': email,
                'password': 'StrongPass1!',
            },
        )
        assert login_resp.status_code == 200
        data = login_resp.json()
        assert 'user' in data
        assert 'user_status' in data['user']
        assert 'session' in data
        assert 'csrf_token' in data

    @pytest.mark.asyncio
    async def test_wrong_password_returns_401(
        self, client: AsyncClient, app: object
    ) -> None:
        """Wrong password returns generic 401."""
        email = await _signup_and_verify(client, app)
        resp = await client.post(
            '/api/v1/auth/login',
            json={
                'email': email,
                'password': 'WrongPass1!',
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_malformed_cookie_is_401(self, client: AsyncClient) -> None:
        """Malformed session cookie yields 401."""
        client.cookies['session_id'] = 'not-a-uuid'
        resp = await client.get('/api/v1/auth/me')
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_excludes_prohibited_fields(
        self, client: AsyncClient, app: object
    ) -> None:
        """Login response excludes prohibited fields."""
        email = await _signup_and_verify(client, app)
        resp = await client.post(
            '/api/v1/auth/login',
            json={
                'email': email,
                'password': 'StrongPass1!',
            },
        )
        data = resp.json()
        user_keys = set(data.get('user', {}).keys())
        excluded = {'password_hash', 'csrf_token_hash', 'ip_address'}
        assert user_keys.isdisjoint(excluded)
