from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    APP_NAME: str = 'questr'
    DEBUG: bool = False
    DATABASE_URL: str = (
        'postgresql+psycopg://app_user:app_password'
        '@questr_database:5432/app_db'
    )

    REDIS_URL: str = 'redis://localhost:6379/0'

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
