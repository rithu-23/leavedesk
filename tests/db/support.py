"""Helpers shared by the database tests: a PostgreSQL-backed app and direct sessions."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from leavedesk.api.main import create_app
from leavedesk.api.settings import Settings
from leavedesk.db.models import TenantRow
from tests.api.support import JWT_SECRET, PASSWORD, RecordingNotifier
from tests.helpers import TODAY

Headers = dict[str, str]


def nov(day: int) -> date:
    return date(2026, 11, day)


def dec(day: int) -> date:
    return date(2026, 12, day)


def postgres_app(database_url: str) -> TestClient:
    """The real API, in PostgreSQL mode, with the test clock and a recording notifier."""
    settings = Settings(
        jwt_secret=JWT_SECRET,  # type: ignore[arg-type]
        demo_password=PASSWORD,  # type: ignore[arg-type]
        database_url=database_url,  # type: ignore[arg-type]
        _env_file=None,  # type: ignore[call-arg]
    )
    return TestClient(create_app(settings, clock=lambda: TODAY, notifiers=[RecordingNotifier()]))


def apply(
    client: TestClient, headers: Headers, start: date, end: date, leave_type: str = "ANNUAL"
) -> str:
    response = client.post(
        "/leave-requests",
        json={
            "leave_type": leave_type,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "reason": "Family trip to Ooty",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


@asynccontextmanager
async def sessions(
    database_url: str,
) -> AsyncIterator[tuple[int, async_sessionmaker[AsyncSession]]]:
    """A session factory on its own engine (its own connections), plus the T-DEMO tenant id."""
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            tenant_pk = await session.scalar(
                select(TenantRow.id).where(TenantRow.public_id == "T-DEMO")
            )
        assert tenant_pk is not None
        yield tenant_pk, factory
    finally:
        await engine.dispose()
