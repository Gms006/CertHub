import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_prefix="", extra="ignore"
    )

    env: str = Field("dev", alias="ENV")
    database_url: str = Field(..., alias="DATABASE_URL")
    default_org_id: int = Field(1, alias="DEFAULT_ORG_ID")
    api_v1_prefix: str = "/api/v1"
    certs_root_path: Path = Field(Path("certs"), alias="CERTS_ROOT_PATH")
    openssl_path: Path = Field(Path("openssl"), alias="OPENSSL_PATH")
    jwt_secret: str = Field(..., alias="JWT_SECRET")
    access_token_ttl_min: int = Field(30, alias="ACCESS_TOKEN_TTL_MIN")
    device_token_ttl_min: int = Field(10, alias="DEVICE_TOKEN_TTL_MIN")
    refresh_ttl_days: int = Field(14, alias="REFRESH_TTL_DAYS")
    set_password_token_ttl_min: int = Field(10, alias="SET_PASSWORD_TOKEN_TTL_MIN")
    reset_password_token_ttl_min: int = Field(30, alias="RESET_PASSWORD_TOKEN_TTL_MIN")
    bcrypt_cost: int = Field(12, alias="BCRYPT_COST")
    retention_keep_until_max_hours: int = Field(24, alias="RETENTION_KEEP_UNTIL_MAX_HOURS")
    lockout_max_attempts: int = Field(5, alias="LOCKOUT_MAX_ATTEMPTS")
    lockout_minutes: int = Field(15, alias="LOCKOUT_MINUTES")
    cookie_secure: bool = Field(True, alias="COOKIE_SECURE")
    cookie_samesite: str = Field("strict", alias="COOKIE_SAMESITE")
    cookie_httponly: bool = Field(True, alias="COOKIE_HTTPONLY")
    allow_legacy_headers: bool = Field(False, alias="ALLOW_LEGACY_HEADERS")
    smtp_host: str | None = Field(None, alias="SMTP_HOST")
    smtp_port: int = Field(587, alias="SMTP_PORT")
    smtp_user: str | None = Field(None, alias="SMTP_USER")
    smtp_pass: str | None = Field(None, alias="SMTP_PASS")
    smtp_from: str | None = Field(None, alias="SMTP_FROM")
    frontend_base_url: str | None = Field(None, alias="FRONTEND_BASE_URL")

    def model_post_init(self, __context) -> None:
        if "COOKIE_SECURE" not in os.environ and self.env.lower() != "prod":
            object.__setattr__(self, "cookie_secure", False)
        if "COOKIE_SAMESITE" not in os.environ and self.env.lower() != "prod":
            object.__setattr__(self, "cookie_samesite", "lax")


settings = Settings()
