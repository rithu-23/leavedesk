"""SPEC FR-12 / FR-13 / FR-14: the PostgreSQL repository through the real API and directly.

These tests commit real data, so each starts from an emptied test database
(the clean_db fixture). They run whether or not DATABASE_URL is set.
"""

from collections.abc import Iterator
from decimal import Decimal

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from leavedesk.db.repository import PostgresLeaveRepository
from leavedesk.domain.exceptions import ConcurrentUpdateError, OverlappingLeaveError
from leavedesk.domain.models import LeaveRequest, LeaveStatus, LeaveType
from tests.api.support import auth_headers
from tests.db.conftest import libpq_url
from tests.db.support import Headers, nov, postgres_app, sessions
from tests.db.support import apply as apply_on


@pytest.fixture
def client(app_database_url: str) -> Iterator[TestClient]:
    with postgres_app(app_database_url) as test_client:
        yield test_client


def apply(client: TestClient, headers: Headers, start: int, end: int) -> str:
    return apply_on(client, headers, nov(start), nov(end))


# ---------- DB-2: durable storage ----------


def test_db2_data_survives_an_api_restart(app_database_url: str) -> None:
    with postgres_app(app_database_url) as first:
        request_id = apply(first, auth_headers(first, "ana@leavedesk.test"), 11, 13)

    with postgres_app(app_database_url) as restarted:  # a brand-new app: nothing in memory
        ana = auth_headers(restarted, "ana@leavedesk.test")
        response = restarted.get(f"/leave-requests/{request_id}", headers=ana)
        assert response.status_code == 200
        assert response.json()["status"] == "pending"
        balances = restarted.get("/employees/E-ANA/balance", headers=ana).json()
        annual = next(b for b in balances if b["leave_type"] == "ANNUAL")
        assert (annual["pending"], annual["available"]) == ("3", "15")
        # start-up seeding is safe to repeat: still exactly three demo logins
        users = restarted.app.state.leavedesk.users  # type: ignore[attr-defined]
        assert users.find_by_email("ANA@leavedesk.test") is not None


# ---------- DB-9: the balance equals the sum of the ledger ----------


def test_db9_balances_equal_the_sum_of_ledger_movements(
    client: TestClient, app_database_url: str
) -> None:
    ana = auth_headers(client, "ana@leavedesk.test")
    mo = auth_headers(client, "mo@leavedesk.test")
    approved = apply(client, ana, 11, 13)
    cancelled = apply(client, ana, 16, 17)
    assert client.post(f"/leave-requests/{approved}/approve", headers=mo).status_code == 200
    assert client.delete(f"/leave-requests/{cancelled}", headers=ana).status_code == 200

    with psycopg.connect(libpq_url(app_database_url)) as conn:
        mismatches = conn.execute(
            """
            SELECT b.id
            FROM leave_balances b
            JOIN leave_ledger l
              ON l.employee_id = b.employee_id AND l.leave_type_id = b.leave_type_id
            GROUP BY b.id, b.entitlement, b.used, b.pending
            HAVING b.entitlement <> sum(l.entitlement_delta)
                OR b.used <> sum(l.used_delta)
                OR b.pending <> sum(l.pending_delta)
            """
        ).fetchall()
        entries = conn.execute(
            """
            SELECT l.entry_type, r.public_id
            FROM leave_ledger l
            JOIN employees e ON e.id = l.employee_id
            LEFT JOIN leave_requests r ON r.id = l.leave_request_id
            WHERE e.public_id = 'E-ANA' AND l.entry_type <> 'grant'
            ORDER BY l.id
            """
        ).fetchall()
    assert mismatches == []
    assert entries == [
        ("reserve", approved),
        ("reserve", cancelled),
        ("confirm", approved),
        ("release", cancelled),
    ]


# ---------- N+1: listing requests uses a fixed number of queries ----------


def count_queries(client: TestClient, path: str, headers: Headers) -> int:
    engine = client.app.state.leavedesk.engine.sync_engine  # type: ignore[attr-defined]
    statements: list[str] = []

    def record(*args: object) -> None:
        statements.append(str(args[2]))

    event.listen(engine, "before_cursor_execute", record)
    try:
        assert client.get(path, headers=headers).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", record)
    return len(statements)


def test_listing_requests_has_no_n_plus_1_queries(client: TestClient) -> None:
    """The query count must not grow with the number of rows (joinedload, lazy="raise")."""
    ana = auth_headers(client, "ana@leavedesk.test")
    mo = auth_headers(client, "mo@leavedesk.test")
    apply(client, ana, 11, 11)
    with_one = count_queries(client, "/leave-requests", mo)
    for day in (12, 13, 16, 17, 18):  # weekdays after TODAY (Monday 9 Nov)
        apply(client, ana, day, day)
    with_six = count_queries(client, "/leave-requests", mo)
    assert with_one == with_six


# ---------- repository-level error translation ----------


async def test_exclude_violation_becomes_overlapping_leave_error(client: TestClient) -> None:
    """Bypass LeaveService's Python check to prove the database rule (EXCLUDE) is mapped to 409."""
    url = client.app.state.leavedesk.settings.database_url.get_secret_value()  # type: ignore[attr-defined]
    async with sessions(url) as (tenant_pk, factory), factory() as session, session.begin():
        repo = PostgresLeaveRepository(session, tenant_pk)
        first = LeaveRequest(
            employee_id="E-ANA",
            leave_type=LeaveType.ANNUAL,
            start_date=nov(11),
            end_date=nov(13),
            reason="Family trip to Ooty",
            days=Decimal("3"),
        )
        await repo.add_request(first)
        clash = first.model_copy(update={"id": "LR-clash", "start_date": nov(13)})
        with pytest.raises(OverlappingLeaveError):
            await repo.add_request(clash)
        await session.rollback()


async def test_db13_stale_update_becomes_concurrent_update_error(client: TestClient) -> None:
    ana = auth_headers(client, "ana@leavedesk.test")
    request_id = apply(client, ana, 11, 13)
    url = client.app.state.leavedesk.settings.database_url.get_secret_value()  # type: ignore[attr-defined]
    async with sessions(url) as (tenant_pk, factory):
        async with factory() as first_session, factory() as second_session:
            first = PostgresLeaveRepository(first_session, tenant_pk)
            second = PostgresLeaveRepository(second_session, tenant_pk)
            # Both read version 1, without locks.
            mine = await first.get_request(request_id)
            theirs = await second.get_request(request_id)

            mine.status = LeaveStatus.CANCELLED
            await first.save_request(mine)
            await first_session.commit()  # version is now 2

            theirs.status = LeaveStatus.APPROVED
            theirs.decided_by = "E-MO"
            with pytest.raises(ConcurrentUpdateError):
                await second.save_request(theirs)  # UPDATE ... WHERE version = 1 -> no row
            await second_session.rollback()

        response = client.get(f"/leave-requests/{request_id}", headers=ana)
        assert response.json()["status"] == "cancelled"  # the first change was kept
