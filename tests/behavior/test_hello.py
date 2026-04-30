"""Behavior tests for the hello endpoint — parametrized time-of-day."""

import pytest
from freezegun import freeze_time
from httpx import AsyncClient


@pytest.mark.parametrize(
    ('time', 'expected_greeting'),
    [
        ('2024-01-01 06:00:00', 'Good morning!'),
        ('2024-01-01 12:00:00', 'Good noon!'),
        ('2024-01-01 15:00:00', 'Good afternoon!'),
        ('2024-01-01 20:00:00', 'Good evening!'),
    ],
)
async def test_hello_with_time(
    time: str, expected_greeting: str, client: AsyncClient
) -> None:
    """Hello endpoint returns the correct greeting based on UTC hour."""
    with freeze_time(time):
        response = await client.get('/api/hello')
        assert response.status_code == 200
        assert response.json() == {'message': expected_greeting}
