from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import AnyUrl, Field
from pydantic import field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import DotEnvSettingsSource, EnvSettingsSource


def _csv_to_list(raw: str) -> list[str]:
    s = raw.strip()
    if not s:
        return []
    if s.startswith("["):
        try:
            import json

            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except Exception:
            pass
    return [x.strip() for x in s.split(",") if x.strip()]


def _is_list_field(field: FieldInfo) -> bool:
    annotation = field.annotation
    if annotation in (list, list[str], list[AnyUrl]):
        return True
    origin = getattr(annotation, "__origin__", None)
    if origin is list:
        return True
    return False


def _patched_prepare(base_cls):
    original = base_cls.prepare_field_value

    def prepare_field_value(self, field_name: str, field: FieldInfo, value: Any, value_is_complex: bool):
        if isinstance(value, str) and _is_list_field(field):
            return _csv_to_list(value)
        return original(self, field_name, field, value, value_is_complex=False)

    base_cls.prepare_field_value = prepare_field_value
    return base_cls


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[2] / ".env"),
        extra="ignore",
        env_parse_none_str="None",
        parse_env_inf_float=False,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        env_settings.__class__ = _patched_prepare(EnvSettingsSource)
        dotenv_settings.__class__ = _patched_prepare(DotEnvSettingsSource)
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )

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
    public_base_url: str | None = None

    mail_enabled: bool = False
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    mail_from: str | None = None
    mail_from_name: str = "MONCAP"

    article_max_attachments: int = 5
    article_max_attachment_mb: int = 20
    article_max_cover_mb: int = 8
    article_allowed_attachment_mimes: list[str] = Field(
        default_factory=lambda: [
            "application/pdf",
            "image/jpeg",
            "image/png",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ],
    )
    article_allowed_cover_mimes: list[str] = Field(
        default_factory=lambda: [
            "image/jpeg",
            "image/png",
            "image/webp",
        ],
    )

    @field_validator("cors_allow_origins", mode="after")
    @classmethod
    def _normalize_cors_origins(cls, v):
        if v is None:
            return []
        return [str(x).strip() for x in v if str(x).strip()]

    @field_validator(
        "article_allowed_attachment_mimes",
        "article_allowed_cover_mimes",
        mode="after",
    )
    @classmethod
    def _normalize_mimes(cls, v):
        if v is None:
            return []
        return [str(x).strip().lower() for x in v if str(x).strip()]

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

    @field_validator("article_allowed_attachment_mimes", "article_allowed_cover_mimes", mode="before")
    @classmethod
    def _split_mime_list(cls, v):
        if isinstance(v, str):
            return [s.strip().lower() for s in v.split(",") if s.strip()]
        if isinstance(v, list):
            return [str(s).strip().lower() for s in v if str(s).strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()

