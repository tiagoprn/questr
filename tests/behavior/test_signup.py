"""Behavior tests for user signup — happy path through HTTP boundary."""

import pytest
from fastapi import status
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
        assert response.status_code == status.HTTP_201_CREATED
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
        assert response.status_code == status.HTTP_409_CONFLICT
        assert 'already exists' in response.json()['detail']

    @pytest.mark.asyncio
    async def test_signup_with_plus_email(self, client: AsyncClient) -> None:
        """Signup with a plus-addressed email succeeds."""
        response = await client.post(
            '/api/v1/auth/signup',
            json={
                'username': 'plususer1',
                'email': 'plususer+tag1@example.com',
                'first_name': 'Plus',
                'last_name': 'User1',
                'password': 'StrongPass1!',
                'password_confirmation': 'StrongPass1!',
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data['email'] == 'plususer+tag1@example.com'

    @pytest.mark.asyncio
    async def test_two_plus_variants_are_distinct(
        self, client: AsyncClient
    ) -> None:
        """Two signups with same base email, different + tags, are distinct."""
        # Create first user with tag1
        response1 = await client.post(
            '/api/v1/auth/signup',
            json={
                'username': 'plususer2a',
                'email': 'baseuser+tag1@example.com',
                'first_name': 'Base',
                'last_name': 'UserA',
                'password': 'StrongPass1!',
                'password_confirmation': 'StrongPass1!',
            },
        )
        assert response1.status_code == status.HTTP_201_CREATED

        # Create second user with tag2 (same base, different tag)
        response2 = await client.post(
            '/api/v1/auth/signup',
            json={
                'username': 'plususer2b',
                'email': 'baseuser+tag2@example.com',
                'first_name': 'Base',
                'last_name': 'UserB',
                'password': 'StrongPass1!',
                'password_confirmation': 'StrongPass1!',
            },
        )
        assert response2.status_code == status.HTTP_201_CREATED

        # Verify they have different IDs
        data1 = response1.json()
        data2 = response2.json()
        assert data1['id'] != data2['id']
        assert data1['email'] == 'baseuser+tag1@example.com'
        assert data2['email'] == 'baseuser+tag2@example.com'
