"""Configuration management for ShortURL Service."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables or defaults."""

    database_url: str = "sqlite+aiosqlite:///./shorturl.db"
    redis_url: str = "redis://localhost:6379/0"
    base_url: str = "http://localhost:8000"
    default_expire_days: int = 30
    short_code_length: int = 6
    # JWT authentication
    secret_key: str = "change-me-in-production-use-a-long-random-string"
    access_token_expire_seconds: int = 86400  # 24 hours

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
