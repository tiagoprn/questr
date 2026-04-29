"""Behavior tests for user signup — happy path through HTTP boundary."""

import pytest
from httpx import AsyncClient


class TestUserSignup:
    @pytest.mark.asyncio
    async def test_happy_path(self, client: AsyncClient) -> None:
        """A new user can sign up successfully."""
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
        assert 'id' in data

    @pytest.mark.asyncio
    async def test_duplicate_username(self, client: AsyncClient) -> None:
        """Signup with an existing username returns 409."""
        payload = {
            'username': 'dupuser',
            'email': 'dupuser@example.com',
            'first_name': 'Dup',
            'last_name': 'User',
            'password': 'StrongPass1!',
            'password_confirmation': 'StrongPass1!',
        }
        await client.post('/api/v1/auth/signup', json=payload)
        response = await client.post('/api/v1/auth/signup', json=payload)
        assert response.status_code == 409
        assert 'already exists' in response.json()['detail']
