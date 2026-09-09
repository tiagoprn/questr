from __future__ import annotations

from questr.settings import Settings


class TestRedisUrl:
    """REDIS_URL composition with and without REDIS_PASSWORD (change 008)."""

    def test_without_password_keeps_dev_url(self) -> None:
        settings = Settings(REDIS_HOST='redis')
        assert settings.REDIS_URL == 'redis://redis:6379/0'

    def test_with_password_embeds_credentials(self) -> None:
        settings = Settings(REDIS_HOST='redis', REDIS_PASSWORD='s3cret')
        assert settings.REDIS_URL == 'redis://:s3cret@redis:6379/0'
