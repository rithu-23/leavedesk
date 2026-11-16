"""Settings from environment variables or a local .env file (never committed)."""

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Each field can be set as an environment variable, e.g. JWT_SECRET=..."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "LeaveDesk API"
    jwt_secret: SecretStr
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = Field(default=30, ge=1, le=1440)
    demo_password: SecretStr
    log_level: str = "INFO"

    # Capstone 3. Unset = in-memory storage (Capstone 2 behaviour). The URL contains the
    # app role's password, so it is a SecretStr and never appears in logs or reprs.
    database_url: SecretStr | None = None
    db_echo: bool = False  # log every SQL statement (N+1 checks)
    tenant_id: str = "T-DEMO"  # SCHEMA.md P2: one tenant at run time
    login_max_attempts: int = Field(default=5, ge=1)  # SPEC BR-13
    login_lock_minutes: int = Field(default=15, ge=1)

    @field_validator("jwt_secret")
    @classmethod
    def secret_is_long_enough(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters long")
        return value

    @field_validator("database_url")
    @classmethod
    def database_url_uses_psycopg(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value().startswith("postgresql+psycopg://"):
            raise ValueError(
                "DATABASE_URL must start with postgresql+psycopg:// (psycopg 3 driver)"
            )
        return value


@lru_cache
def get_settings() -> Settings:
    """Read the settings once and reuse them."""
    return Settings()  # type: ignore[call-arg]  # required values come from the environment
