"""Fixtures for tests that need a real PostgreSQL database (Capstone 3).

They run against the *test* database (leavedesk_test), never the main one, using:
  TEST_MIGRATION_DATABASE_URL  as leavedesk_migrator (DDL, used to migrate)
  TEST_DATABASE_URL            as leavedesk_app (data only, like the API)
read from the environment or .env. If either is missing, every test in tests/db
is skipped, so `pytest` still works on a machine without Docker.

Each test gets connections inside a transaction that is rolled back afterwards,
so tests never see each other's rows.
"""

from collections.abc import Iterator

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class TestDatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    test_database_url: SecretStr | None = None
    test_migration_database_url: SecretStr | None = None


SETTINGS = TestDatabaseSettings()


def _require(url: SecretStr | None) -> str:
    if url is None:
        pytest.skip("TEST_DATABASE_URL / TEST_MIGRATION_DATABASE_URL not set (see README)")
    return url.get_secret_value()


def libpq_url(sqlalchemy_url: str) -> str:
    """psycopg.connect() wants postgresql://...; SQLAlchemy URLs name the driver too."""
    return sqlalchemy_url.replace("postgresql+psycopg://", "postgresql://", 1)


@pytest.fixture(scope="session")
def alembic_config() -> Config:
    config = Config("alembic.ini")
    # configparser treats % as special, so a password containing % must be doubled.
    url = _require(SETTINGS.test_migration_database_url)
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


@pytest.fixture(scope="session")
def migrated(alembic_config: Config) -> Config:
    """Rebuild the test database from scratch once per test run: base, then head."""
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
    return alembic_config


@pytest.fixture
def migrator(migrated: Config) -> Iterator[psycopg.Connection]:
    """A connection as leavedesk_migrator inside a transaction that is rolled back."""
    url = _require(SETTINGS.test_migration_database_url)
    with psycopg.connect(libpq_url(url)) as conn:
        yield conn
        conn.rollback()


@pytest.fixture
def app(migrated: Config) -> Iterator[psycopg.Connection]:
    """A connection as leavedesk_app (the API's role) inside a transaction that is rolled back."""
    url = _require(SETTINGS.test_database_url)
    with psycopg.connect(libpq_url(url)) as conn:
        yield conn
        conn.rollback()


@pytest.fixture
def clean_db(migrated: Config) -> None:
    """Empty the business tables (seed rows stay), for tests that commit real data."""
    url = _require(SETTINGS.test_migration_database_url)
    with psycopg.connect(libpq_url(url), autocommit=True) as conn:
        conn.execute(
            "TRUNCATE employees, users, leave_requests, leave_balances, leave_ledger, "
            "audit_log, notifications RESTART IDENTITY CASCADE"
        )


@pytest.fixture
def app_database_url(clean_db: None) -> str:
    """The app role's SQLAlchemy URL for the test database, on an emptied database."""
    return _require(SETTINGS.test_database_url)
