"""Alembic environment: runs migrations as the migrator role (SCHEMA.md 6).

Migrations use a plain synchronous connection: they are a one-off command,
not a server, so there is no event loop to keep free. psycopg 3 serves both
the sync (here) and async (the app) engines from the same URL scheme.

URL lookup order:
1. sqlalchemy.url set on the Config by the caller (the test suite does this);
2. MIGRATION_DATABASE_URL from the environment or .env.
"""

from logging.config import fileConfig

from alembic import context
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, pool

from leavedesk.db import models  # noqa: F401  (registers every table on Base.metadata)
from leavedesk.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


class MigrationSettings(BaseSettings):
    """Only what migrations need, so Alembic does not require JWT_SECRET and friends."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    migration_database_url: SecretStr


def database_url() -> str:
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    return MigrationSettings().migration_database_url.get_secret_value()  # type: ignore[call-arg]


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql`: print the SQL instead of running it."""
    context.configure(url=database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
