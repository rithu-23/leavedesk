"""SPEC FR-12 / FR-13 / FR-17: rules the database itself enforces (SCHEMA.md).

Rows are inserted directly in SQL, without LeaveService, to prove the database
blocks bad data even if the application had a bug. A failing statement is run
inside `with conn.transaction():` (a savepoint), so the test's outer transaction
stays usable after the expected error.
"""

from datetime import date

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import errors

TENANT = "(SELECT id FROM tenants WHERE public_id = 'T-DEMO')"
ANNUAL = "(SELECT id FROM leave_types WHERE code = 'ANNUAL')"


def add_employee(conn: psycopg.Connection, public_id: str, email: str, tenant: str = TENANT) -> int:
    row = conn.execute(
        f"INSERT INTO employees (tenant_id, public_id, name, email, role) "
        f"VALUES ({tenant}, %s, %s, %s, 'employee') RETURNING id",
        (public_id, public_id, email),
    ).fetchone()
    assert row is not None
    return int(row[0])


def add_request(
    conn: psycopg.Connection,
    employee_id: int,
    start: date,
    end: date,
    *,
    public_id: str = "LR-1",
    status: str = "pending",
    days: str = "3",
    half_day: bool = False,
    reason: str = "Family trip to Ooty",
) -> None:
    conn.execute(
        f"INSERT INTO leave_requests (tenant_id, public_id, employee_id, leave_type_id, "
        f"start_date, end_date, half_day, reason, status, days, decision_note) "
        f"VALUES ({TENANT}, %s, %s, {ANNUAL}, %s, %s, %s, %s, %s, %s, %s)",
        (
            public_id,
            employee_id,
            start,
            end,
            half_day,
            reason,
            status,
            days,
            "Team deadline" if status == "rejected" else None,
        ),
    )


def nov(day: int) -> date:
    return date(2026, 11, day)


# ---------- FR-12: migrations ----------


def test_db3_upgrade_downgrade_upgrade_and_models_match(migrated: Config) -> None:
    command.downgrade(migrated, "base")
    command.upgrade(migrated, "head")
    command.check(migrated)  # raises if the models and the database differ


def test_seed_rows_match_the_domain(app: psycopg.Connection) -> None:
    rows = app.execute(
        "SELECT code, default_entitlement, max_days_per_request FROM leave_types ORDER BY code"
    ).fetchall()
    assert [(code, str(ent), str(cap) if cap else None) for code, ent, cap in rows] == [
        ("ANNUAL", "18.0", None),
        ("CASUAL", "6.0", "2.0"),
        ("SICK", "12.0", None),
    ]
    assert app.execute("SELECT count(*) FROM tenants WHERE public_id = 'T-DEMO'").fetchone() == (1,)


# ---------- FR-13: CHECK, UNIQUE, EXCLUDE ----------


@pytest.mark.parametrize(
    ("label", "start", "end", "kwargs"),
    [
        ("DB-4 end before start", nov(13), nov(11), {}),
        ("half day across two dates", nov(11), nov(12), {"half_day": True, "days": "0.5"}),
        ("reason too short", nov(11), nov(11), {"reason": "trip", "days": "1"}),
        ("unknown status", nov(11), nov(11), {"status": "maybe", "days": "1"}),
        ("not a half-day step", nov(11), nov(11), {"days": "0.3"}),
    ],
)
def test_check_constraints_reject_bad_requests(
    app: psycopg.Connection, label: str, start: date, end: date, kwargs: dict[str, object]
) -> None:
    ana = add_employee(app, "E-ANA", "ana@leavedesk.test")
    with pytest.raises(errors.CheckViolation), app.transaction():
        add_request(app, ana, start, end, **kwargs)  # type: ignore[arg-type]


def test_balance_can_never_exceed_entitlement(app: psycopg.Connection) -> None:
    """BR-4's last line of defence: used + pending <= entitlement."""
    ana = add_employee(app, "E-ANA", "ana@leavedesk.test")
    with pytest.raises(errors.CheckViolation), app.transaction():
        app.execute(
            f"INSERT INTO leave_balances (tenant_id, employee_id, leave_type_id, "
            f"entitlement, used, pending) VALUES ({TENANT}, %s, {ANNUAL}, 18, 15, 4)",
            (ana,),
        )


def test_db5_email_unique_per_tenant_ignoring_case(app: psycopg.Connection) -> None:
    add_employee(app, "E-ANA", "ana@leavedesk.test")
    with pytest.raises(errors.UniqueViolation), app.transaction():
        add_employee(app, "E-ANA2", "ANA@LeaveDesk.test")

    app.execute("INSERT INTO tenants (public_id, name) VALUES ('T-OTHER', 'Other company')")
    add_employee(
        app,
        "E-ANA",
        "ANA@LeaveDesk.test",
        tenant="(SELECT id FROM tenants WHERE public_id = 'T-OTHER')",
    )  # same email and public id in another tenant: allowed


def test_db6_overlapping_pending_or_approved_leave_is_excluded(app: psycopg.Connection) -> None:
    ana = add_employee(app, "E-ANA", "ana@leavedesk.test")
    add_request(app, ana, nov(11), nov(13), public_id="LR-1")
    with pytest.raises(errors.ExclusionViolation), app.transaction():
        add_request(app, ana, nov(13), nov(13), public_id="LR-2", days="1")  # shares 13 Nov


def test_db6_cancelled_and_rejected_requests_do_not_block(app: psycopg.Connection) -> None:
    ana = add_employee(app, "E-ANA", "ana@leavedesk.test")
    add_request(app, ana, nov(11), nov(13), public_id="LR-1", status="cancelled")
    add_request(app, ana, nov(11), nov(13), public_id="LR-2", status="rejected")
    add_request(app, ana, nov(12), nov(12), public_id="LR-3", days="1")  # accepted


def test_overlap_is_per_employee(app: psycopg.Connection) -> None:
    ana = add_employee(app, "E-ANA", "ana@leavedesk.test")
    mo = add_employee(app, "E-MO", "mo@leavedesk.test")
    add_request(app, ana, nov(11), nov(13), public_id="LR-1")
    add_request(app, mo, nov(11), nov(13), public_id="LR-2")  # different employee: fine


# ---------- FR-13: append-only ledger (DB-8) ----------


def test_db8_ledger_is_append_only(app: psycopg.Connection, migrator: psycopg.Connection) -> None:
    ana = add_employee(app, "E-ANA", "ana@leavedesk.test")
    app.execute(
        f"INSERT INTO leave_ledger (tenant_id, employee_id, leave_type_id, entry_type, "
        f"entitlement_delta) VALUES ({TENANT}, %s, {ANNUAL}, 'grant', 18)",
        (ana,),
    )
    app.commit()  # make the row visible to the migrator's connection
    try:
        for statement in ("UPDATE leave_ledger SET used_delta = 1", "DELETE FROM leave_ledger"):
            with pytest.raises(errors.InsufficientPrivilege), app.transaction():
                app.execute(statement)  # layer 1: the app role has no UPDATE/DELETE grant

        with pytest.raises(errors.RestrictViolation, match="append-only"), migrator.transaction():
            migrator.execute("UPDATE leave_ledger SET used_delta = 1")  # layer 2: the trigger
    finally:
        # Clean up the committed rows. TRUNCATE does not fire row triggers.
        migrator.rollback()
        migrator.execute("TRUNCATE leave_ledger, employees CASCADE")
        migrator.commit()


# ---------- FR-17: roles (DB-14, DB-29) ----------


def test_db14_app_role_has_timeouts(app: psycopg.Connection) -> None:
    assert app.execute("SHOW statement_timeout").fetchone() == ("5s",)
    assert app.execute("SHOW lock_timeout").fetchone() == ("2s",)
    assert app.execute("SHOW idle_in_transaction_session_timeout").fetchone() == ("10s",)


def test_db29_app_role_cannot_change_the_schema(app: psycopg.Connection) -> None:
    with pytest.raises(errors.InsufficientPrivilege), app.transaction():
        app.execute("CREATE TABLE sneaky (id int)")
    with pytest.raises(errors.InsufficientPrivilege), app.transaction():
        app.execute("ALTER TABLE leave_requests DROP CONSTRAINT leave_requests_no_overlap")


# ---------- SCHEMA.md 5.1: every foreign key is indexed (DB-30) ----------


def test_db30_every_foreign_key_column_leads_an_index(app: psycopg.Connection) -> None:
    unindexed = app.execute(
        """
        SELECT c.conrelid::regclass::text, a.attname
        FROM pg_constraint c
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
        WHERE c.contype = 'f'
          AND NOT EXISTS (
            SELECT 1 FROM pg_index i
            WHERE i.indrelid = c.conrelid AND i.indkey[0] = c.conkey[1]
          )
        ORDER BY 1, 2
        """
    ).fetchall()
    assert unindexed == []


# ---------- SCHEMA.md 7: optimistic locking is configured ----------


def test_version_columns_are_wired_for_optimistic_locking() -> None:
    """Regression test (AI_NOTES Entry 11): a string version_id_col is silently ignored."""
    from sqlalchemy import Column
    from sqlalchemy.orm import configure_mappers

    from leavedesk.db.models import LeaveBalanceRow, LeaveRequestRow

    configure_mappers()
    for model in (LeaveRequestRow, LeaveBalanceRow):
        column = model.__mapper__.version_id_col
        assert isinstance(column, Column)
        assert column.name == "version"
