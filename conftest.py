"""Run the whole test suite against PostgreSQL when DATABASE_URL is set (SPEC DB-1).

    pytest                          -> in-memory storage (fast, no Docker needed)
    scripts/pytest-postgres.sh      -> the same tests on the leavedesk_test database

How the unchanged Day 2 API tests end up on PostgreSQL: their fixture builds
Settings(_env_file=None), which ignores .env but still reads environment
variables, so DATABASE_URL in the environment switches create_app() to the
PostgreSQL repository. This file only prepares the database:
- once per run: `alembic upgrade head` on the test database;
- before every test: empty the tables that tests write to, so each test starts
  from the same state as the in-memory repository (seed rows stay).

Safety: it refuses to run unless DATABASE_URL points at a database whose name
ends in "_test", so it can never empty the real database.
"""

import os
from collections.abc import Iterator
from urllib.parse import urlsplit

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

RESET_TABLES = (
    "employees",
    "users",
    "leave_requests",
    "leave_balances",
    "leave_ledger",
    "audit_log",
    "notifications",
)


class _MigrationUrl(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    test_migration_database_url: SecretStr | None = None


def _database_url() -> str | None:
    return os.environ.get("DATABASE_URL")


@pytest.fixture(scope="session")
def _postgres_migration_url() -> str | None:
    url = _database_url()
    if url is None:
        return None
    database = urlsplit(url).path.lstrip("/")
    if not database.endswith("_test"):
        pytest.exit(f"Refusing to run tests against database {database!r}: it must end in _test")
    migration_url = _MigrationUrl().test_migration_database_url
    if migration_url is None:
        pytest.exit("DATABASE_URL is set but TEST_MIGRATION_DATABASE_URL is not (see README)")
    value = migration_url.get_secret_value()
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", value.replace("%", "%%"))
    command.upgrade(config, "head")
    return value


@pytest.fixture(autouse=True)
def _fresh_postgres_tables(_postgres_migration_url: str | None) -> Iterator[None]:
    """Empty the business tables before each test (PostgreSQL runs only).

    TRUNCATE is used because it is instant and resets identity counters; it does
    not fire the append-only row triggers, and only the schema owner (migrator)
    may run it, never the app role (SCHEMA.md 4.8).
    """
    if _postgres_migration_url is not None:
        libpq_url = _postgres_migration_url.replace("postgresql+psycopg://", "postgresql://", 1)
        with psycopg.connect(libpq_url, autocommit=True) as connection:
            connection.execute(f"TRUNCATE {', '.join(RESET_TABLES)} RESTART IDENTITY CASCADE")
    yield
