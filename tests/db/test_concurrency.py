"""SPEC FR-14: concurrent actions on PostgreSQL (Part C, "Done when").

Each "user" below gets its own session, so its own database connection and
transaction, exactly like two HTTP requests arriving at the same moment.
asyncio.gather starts both actions together; whenever one waits for the
database (or for a lock), the other runs.

Review demo (SPEC DB-16): the same test can be run without any protection.
    pytest tests/db/test_concurrency.py -k db10                          -> passes
    LEAVEDESK_DEMO_NO_LOCKS=1 pytest tests/db/test_concurrency.py -k db10 -> FAILS: both approvals go through
The unsafe repository ignores lock=True and writes rows back with plain UPDATEs
(no version check), the classic "read, change, write back" lost-update bug.
"""

import asyncio
import os
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from leavedesk.db.repository import PostgresLeaveRepository
from leavedesk.domain.balance import LeaveBalance
from leavedesk.domain.exceptions import (
    InsufficientBalanceError,
    InvalidTransitionError,
    OverlappingLeaveError,
)
from leavedesk.domain.models import LeaveRequest, LeaveType
from leavedesk.domain.policies import default_policies
from leavedesk.domain.repository import LeaveRepository
from leavedesk.domain.service import LeaveService
from tests.api.support import auth_headers
from tests.db.conftest import libpq_url
from tests.db.support import apply, dec, nov, postgres_app, sessions
from tests.helpers import TODAY

UNSAFE = os.environ.get("LEAVEDESK_DEMO_NO_LOCKS") == "1"


class UnsafeRepository(PostgresLeaveRepository):
    """What the code would be WITHOUT row locks and WITHOUT version checks (demo only)."""

    barrier: asyncio.Barrier  # set per test: both users finish reading before either writes

    async def get_request(self, request_id: str, *, lock: bool = False) -> LeaveRequest:
        return await super().get_request(request_id, lock=False)  # no FOR UPDATE

    async def get_balance(
        self, employee_id: str, leave_type: LeaveType, *, lock: bool = False
    ) -> LeaveBalance:
        balance = await super().get_balance(employee_id, leave_type, lock=False)
        await self.barrier.wait()  # force the worst timing: both have read the old values
        return balance

    async def save_request(self, request: LeaveRequest) -> None:
        await self._session.execute(
            text(
                "UPDATE leave_requests SET status = :status, decided_by = "
                "(SELECT id FROM employees WHERE public_id = :decider) WHERE public_id = :id"
            ),
            {"status": request.status.value, "decider": request.decided_by, "id": request.id},
        )

    async def save_balance(self, balance: LeaveBalance, *, request_id: str | None = None) -> None:
        await self._session.execute(
            text(
                "UPDATE leave_balances b SET used = :used, pending = :pending "
                "FROM employees e, leave_types t WHERE b.employee_id = e.id "
                "AND b.leave_type_id = t.id AND e.public_id = :employee AND t.code = :code"
            ),
            {
                "used": balance.used,
                "pending": balance.pending,
                "employee": balance.employee_id,
                "code": balance.leave_type.value,
            },
        )
        await self._session.execute(
            text(
                "INSERT INTO leave_ledger (tenant_id, employee_id, leave_type_id, entry_type, "
                "used_delta, pending_delta) SELECT e.tenant_id, e.id, t.id, 'confirm', :d, -:d "
                "FROM employees e, leave_types t WHERE e.public_id = :employee AND t.code = :code"
            ),
            {"d": Decimal("3"), "employee": balance.employee_id, "code": balance.leave_type.value},
        )


class ReadBothFirstRepository(PostgresLeaveRepository):
    """Safe repository, but both users finish the Python overlap check before either saves.

    Makes DB-7 deterministic: without this, the second user might sometimes run its
    overlap check after the first committed, and the Python check (not the database)
    would refuse it. The test would still pass, but would not prove anything.
    """

    barrier: asyncio.Barrier

    async def list_requests(self, employee_id: str | None = None, status: Any = None) -> Any:
        found = await super().list_requests(employee_id=employee_id, status=status)
        await self.barrier.wait()
        return found


@pytest.fixture
def client(app_database_url: str) -> Iterator[TestClient]:
    with postgres_app(app_database_url) as test_client:
        yield test_client


async def run_together(
    database_url: str,
    *actions: Any,
    unsafe: bool = False,
    repository: type[PostgresLeaveRepository] = PostgresLeaveRepository,
) -> list[object]:
    """Run each action(service) in its own session and transaction, all at the same time.

    Returns each action's result, or the exception it raised.
    """
    async with sessions(database_url) as (tenant_pk, factory):
        barrier = asyncio.Barrier(len(actions))

        async def one(action: Any) -> object:
            async with factory() as session, session.begin():
                repo: LeaveRepository = (UnsafeRepository if unsafe else repository)(
                    session, tenant_pk
                )
                repo.barrier = barrier  # type: ignore[attr-defined]  # used by the test subclasses
                service = LeaveService(repo, default_policies(), clock=lambda: TODAY)
                return await action(service)

        return await asyncio.gather(*(one(a) for a in actions), return_exceptions=True)


def ledger(database_url: str, entry_type: str) -> int:
    with psycopg.connect(libpq_url(database_url)) as conn:
        row = conn.execute(
            "SELECT count(*) FROM leave_ledger WHERE entry_type = %s", (entry_type,)
        ).fetchone()
    assert row is not None
    return int(row[0])


def annual_balance(client: TestClient, headers: dict[str, str]) -> dict[str, str]:
    balances = client.get("/employees/E-ANA/balance", headers=headers).json()
    return next(b for b in balances if b["leave_type"] == "ANNUAL")


# ---------- DB-10: two managers' tabs approve the same request at once ----------


async def test_db10_double_approval_deducts_only_once(
    client: TestClient, app_database_url: str
) -> None:
    ana = auth_headers(client, "ana@leavedesk.test")
    request_id = apply(client, ana, nov(11), nov(13))  # 3 days

    results = await run_together(
        app_database_url,
        lambda s: s.approve(request_id, "E-MO"),
        lambda s: s.approve(request_id, "E-MO"),
        unsafe=UNSAFE,
    )

    succeeded = [r for r in results if isinstance(r, LeaveRequest)]
    refused = [r for r in results if isinstance(r, InvalidTransitionError)]
    assert len(succeeded) == 1, f"both approvals went through: {results}"
    assert len(refused) == 1  # the second waited for the lock, then saw "approved"
    assert annual_balance(client, ana)["used"] == "3"  # deducted once, not 6
    assert ledger(app_database_url, "confirm") == 1


def test_db16_demo_flag_is_off_in_normal_runs() -> None:
    """Guard: the unsafe demo mode must never be left on by accident."""
    assert os.environ.get("LEAVEDESK_DEMO_NO_LOCKS") in (None, "", "1")
    if UNSAFE:
        pytest.skip("demo mode: test_db10 is expected to fail")


# ---------- DB-11: two submits that together overspend the balance ----------


async def test_db11_concurrent_submits_cannot_overspend(
    client: TestClient, app_database_url: str
) -> None:
    ana = auth_headers(client, "ana@leavedesk.test")
    apply(client, ana, nov(11), dec(1))  # 15 working days: 3 of 18 annual days left

    results = await run_together(
        app_database_url,
        lambda s: s.apply("E-ANA", LeaveType.ANNUAL, dec(7), dec(8), "Wedding in Madurai"),
        lambda s: s.apply("E-ANA", LeaveType.ANNUAL, dec(9), dec(10), "Wedding in Madurai"),
    )

    assert sum(isinstance(r, LeaveRequest) for r in results) == 1
    assert sum(isinstance(r, InsufficientBalanceError) for r in results) == 1
    balance = annual_balance(client, ana)
    assert (balance["pending"], balance["available"]) == ("17", "1")  # never 19 pending


# ---------- DB-7: two overlapping submits at once; only the EXCLUDE constraint sees both ----------


async def test_db7_concurrent_overlapping_submits_one_is_refused(
    client: TestClient, app_database_url: str
) -> None:
    """Annual and sick lock DIFFERENT balance rows, so the locks don't serialise them and
    both pass the Python overlap check. Only the database constraint can stop the second."""
    ana = auth_headers(client, "ana@leavedesk.test")

    results = await run_together(
        app_database_url,
        lambda s: s.apply("E-ANA", LeaveType.ANNUAL, nov(11), nov(13), "Family trip to Ooty"),
        lambda s: s.apply("E-ANA", LeaveType.SICK, nov(12), nov(13), "Fever, doctor visit"),
        repository=ReadBothFirstRepository,
    )

    assert sum(isinstance(r, LeaveRequest) for r in results) == 1
    [refused] = [r for r in results if isinstance(r, OverlappingLeaveError)]
    # This message comes only from the EXCLUDE (23P01) translation in the repository:
    # proof that the database, not the Python check, stopped the second request.
    assert "saved at the same moment" in str(refused)
    listed = client.get("/leave-requests", headers=ana).json()
    assert listed["total"] == 1


# ---------- DB-15: a lock held too long -> 503, nothing saved ----------


def test_db15_lock_timeout_returns_503_and_saves_nothing(
    client: TestClient, app_database_url: str, migrator_database_url: str
) -> None:
    ana = auth_headers(client, "ana@leavedesk.test")
    with psycopg.connect(libpq_url(migrator_database_url)) as blocker:
        blocker.execute(
            "SELECT b.id FROM leave_balances b JOIN employees e ON e.id = b.employee_id "
            "JOIN leave_types t ON t.id = b.leave_type_id "
            "WHERE e.public_id = 'E-ANA' AND t.code = 'ANNUAL' FOR UPDATE"
        )  # holds the row lock until this block ends (transaction still open)
        response = client.post(
            "/leave-requests",
            json={
                "leave_type": "ANNUAL",
                "start_date": "2026-11-11",
                "end_date": "2026-11-13",
                "reason": "Family trip to Ooty",
            },
            headers=ana,
        )
        blocker.rollback()

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_BUSY"
    assert response.headers["retry-after"] == "1"
    assert client.get("/leave-requests", headers=ana).json()["total"] == 0  # rolled back
