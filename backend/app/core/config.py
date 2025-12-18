from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_prefix="", extra="ignore"
    )

    database_url: str = Field(..., alias="DATABASE_URL")
    api_v1_prefix: str = "/api/v1"
    certs_root_path: Path = Field(Path("certs"), alias="CERTS_ROOT_PATH")
    openssl_path: Path = Field(Path("openssl"), alias="OPENSSL_PATH")


settings = Settings()
