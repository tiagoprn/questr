from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    APP_NAME: str = 'questr'
    DEBUG: bool = False
    DATABASE_URL: str = 'postgresql+psycopg://app_user:app_password@questr_database:5432/app_db'

    model_config = {'env_file': '.env', 'extra': 'ignore'}


settings = Settings()
