from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    APP_NAME: str = 'questr'
    DEBUG: bool = False
    POSTGRES_USER: str = 'questr'
    POSTGRES_PASSWORD: str = 'qB2xSEEJ-Q.UI3'
    POSTGRES_DB: str = 'questr_db'
    POSTGRES_HOST: str = '127.0.0.1'
    REDIS_HOST: str = '127.0.0.1'

    @property
    def DATABASE_URL(self) -> str:
        return (
            f'postgresql+psycopg://{self.POSTGRES_USER}'
            f':{self.POSTGRES_PASSWORD}'
            f'@{self.POSTGRES_HOST}:5432/{self.POSTGRES_DB}'
        )

    @property
    def REDIS_URL(self) -> str:
        return f'redis://{self.REDIS_HOST}:6379/0'

    EMAIL_ENABLED: bool = False
    SMTP_HOST: str = 'localhost'
    SMTP_PORT: int = 1025
    SMTP_USER: str = ''
    SMTP_PASSWORD: str = ''
    EMAIL_FROM: str = 'noreply@questr.app'

    RATE_LIMIT_RESEND_MAX: int = 3
    RATE_LIMIT_RESEND_WINDOW_HOURS: int = 1

    model_config = {'env_file': '.env', 'extra': 'ignore'}


settings = Settings()
