from typing import Literal

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
    SMTP_USE_STARTTLS: bool = True
    EMAIL_FROM: str = 'noreply@questr.app'

    APP_URL: str = 'http://localhost:8000'
    RATE_LIMIT_RESEND_MAX: int = 3
    RATE_LIMIT_RESEND_WINDOW_HOURS: int = 1

    # Login throttling
    LOGIN_PER_ACCOUNT_MAX_ATTEMPTS: int = 5
    LOGIN_PER_ACCOUNT_WINDOW_MINUTES: int = 15
    LOGIN_LOCKOUT_MINUTES: int = 30
    LOGIN_PER_IP_MAX_ATTEMPTS: int = 20
    LOGIN_PER_IP_WINDOW_MINUTES: int = 10

    # Session lifetime
    SESSION_IDLE_MINUTES: int = 30
    SESSION_ABSOLUTE_HOURS: int = 8
    SESSION_REMEMBER_DAYS: int = 30

    # Session caps
    MAX_CONCURRENT_SESSIONS: int = 10

    # Environment discriminator. Pydantic validates this Literal at
    # load time, so typos (e.g. ENVIRONMENT=production) fail with a
    # clear validation error. Default is 'dev' because the current
    # .env uses an HTTP APP_URL. Production deployments MUST set
    # ENVIRONMENT=prod explicitly.
    ENVIRONMENT: Literal['dev', 'prod'] = 'dev'

    # Cookie security.
    #
    # NOTE: SECURE_COOKIE is a computed property, NOT a regular
    # settings field. It is derived from ENVIRONMENT and is LOCKED
    # to True in production. Setting SECURE_COOKIE in the
    # environment or .env has no effect -- the property always
    # wins.
    #
    # Rationale:
    # - The Secure flag instructs clients (browsers, hurl/libcurl)
    #   to only transmit the cookie over HTTPS.
    # - In dev (HTTP), the Secure flag would prevent cookies from
    #   being sent, which breaks the auth flow: login sets a
    #   session_id cookie that subsequent requests (/me, logout)
    #   depend on.
    # - In prod (HTTPS), the Secure flag is a security requirement
    #   to prevent cookie theft over plaintext connections.
    #
    # To switch behavior, set ENVIRONMENT=dev or ENVIRONMENT=prod.
    # Do NOT try to set SECURE_COOKIE directly; it is ignored.
    @property
    def SECURE_COOKIE(self) -> bool:
        return self.ENVIRONMENT == 'prod'

    @property
    def app_url(self) -> str:
        return self.APP_URL.rstrip('/')

    model_config = {'env_file': '.env', 'extra': 'ignore'}


settings = Settings()
