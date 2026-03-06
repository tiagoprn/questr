import pytest
from freezegun import freeze_time
from httpx import ASGITransport, AsyncClient

from questr.factory import create_app


@pytest.mark.parametrize(
    ("time", "expected_greeting"),
    [
        ("2024-01-01 00:00:00", "Good morning!"),
        ("2024-01-01 06:00:00", "Good morning!"),
        ("2024-01-01 11:59:59", "Good morning!"),
        ("2024-01-01 12:00:00", "Good noon!"),
        ("2024-01-01 13:00:00", "Good afternoon!"),
        ("2024-01-01 17:59:59", "Good afternoon!"),
        ("2024-01-01 18:00:00", "Good evening!"),
        ("2024-01-01 23:59:59", "Good evening!"),
    ],
)
async def test_hello_endpoint(time: str, expected_greeting: str) -> None:
    """Test hello endpoint returns correct greeting based on time."""
    with freeze_time(time):
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.get("/api/hello")
            assert response.status_code == 200  # noqa: PLR2004
            assert response.json() == {"message": expected_greeting}
