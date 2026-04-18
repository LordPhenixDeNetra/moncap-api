from functools import lru_cache
from typing import Literal

from pydantic import AnyUrl, Field
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    api_title: str = "MONCAP API"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/moncap"

    jwt_issuer: str = "moncap-api"
    jwt_audience: str = "moncap-admin"
    jwt_secret: str = Field(min_length=32)
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 60 * 60 * 24 * 14

    cors_allow_origins: list[AnyUrl] = []
    cors_allow_credentials: bool = True

    refresh_cookie_name: str = "moncap_refresh"
    refresh_cookie_secure: bool = True
    refresh_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    refresh_cookie_path: str = "/api/v1/auth"

    storage_dir: str = "storage"
    public_files_path: str = "/files"

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        if v.startswith("postgresql+psycopg2://"):
            return v.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
