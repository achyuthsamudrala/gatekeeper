"""Application settings via pydantic-settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "GATEKEEPER_", "env_file": ".env", "extra": "ignore"}

    database_url: str = "postgresql+asyncpg://gatekeeper:gatekeeper@db:5432/gatekeeper"
    config_path: str = "/config/server.yaml"
    secret: str = "changeme"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"

    # LLM Judge defaults (overridden by server.yaml)
    anthropic_api_key: str = ""
    model_api_key: str = ""


settings = Settings()
