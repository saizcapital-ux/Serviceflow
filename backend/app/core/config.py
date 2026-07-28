"""Application configuration (12-factor, read from environment)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SERVICEFLOW_", env_file=".env", extra="ignore")

    app_name: str = "Serviceflow"
    environment: str = "development"

    # Database — SQLite by default for zero-config dev; set DATABASE_URL for Postgres.
    database_url: str = "sqlite:///./serviceflow.db"

    # Security
    secret_key: str = "dev-secret-change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_ttl_min: int = 720  # 12 hours

    # CORS — comma-separated origins, or "*" for dev.
    cors_origins: str = "*"

    # File storage — "local" (default) or "s3". Local files live under storage_dir.
    storage_backend: str = "local"
    storage_dir: str = "./uploads"
    s3_bucket: str = ""
    s3_region: str = "us-east-1"

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
