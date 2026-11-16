"""Index proof for PERF.md (SPEC DB-31): seed ~100,000 leave requests, then capture
EXPLAIN (ANALYZE, BUFFERS) for each query before and after revision 0003.

    python scripts/perf.py            # writes perf_results.txt (not committed)

Runs ONLY against the test database (TEST_MIGRATION_DATABASE_URL in .env, name must
end in _test). It migrates that database to 0002, empties it, seeds, measures,
migrates to head (0003 adds the indexes), measures again. The next test run empties
it again, so nothing needs cleaning up.

"Before" plans run inside a transaction that is always rolled back:
BEGIN; DROP INDEX ix_leave_requests_employee_id;
       ALTER TABLE leave_requests DROP CONSTRAINT leave_requests_no_overlap;
       EXPLAIN ...; ROLLBACK;
Both of those structures contain employee_id (the GiST index behind the EXCLUDE
constraint can serve employee_id = ... thanks to btree_gist), so they are removed to
see the query with no supporting index at all. PostgreSQL DDL is transactional, so
nothing is really dropped (SCHEMA.md 5.2). A third run keeps the EXCLUDE index, to
show what the planner does with only the indexes that Part A requires.
"""

import sys
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

EMPLOYEES = 20_000  # 200 managers + 19,800 employees
REQUESTS_PER_EMPLOYEE = 5  # -> 100,000 leave requests
OUTPUT = Path("perf_results.txt")


class _Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    test_migration_database_url: SecretStr


SEED_SQL = f"""
TRUNCATE employees, users, leave_requests, leave_balances, leave_ledger, audit_log,
         notifications RESTART IDENTITY CASCADE;

-- Managers P-1..P-200, then employees P-201..P-{EMPLOYEES}, each reporting to one manager.
-- Names mix 40 first names and 40 surnames; every 1000th person is a 'Ramaswamy', so a
-- search for '%aswam%' matches ~20 of {EMPLOYEES} people (a selective search).
INSERT INTO employees (tenant_id, public_id, name, email, role)
SELECT t.id, 'P-' || g, 'Manager ' || g, 'm' || g || '@perf.test', 'manager'
FROM tenants t, generate_series(1, 200) g WHERE t.public_id = 'T-DEMO';

INSERT INTO employees (tenant_id, public_id, name, email, role, manager_id)
SELECT t.id, 'P-' || g,
       (ARRAY['Asha','Bala','Chitra','Deepak','Esha','Farhan','Gita','Hari','Indu','Jai',
              'Kavya','Lakshmi','Mani','Nila','Om','Priya','Ravi','Sita','Tara','Uma',
              'Varun','Wasim','Yash','Zara','Arjun','Bhavna','Charan','Divya','Ganesh','Hema',
              'Ishaan','Jaya','Kiran','Leela','Mohan','Nandini','Pooja','Rahul','Sanjay','Vani'])
         [1 + g % 40] || ' ' ||
       CASE WHEN g % 1000 = 0 THEN 'Ramaswamy' ELSE
       (ARRAY['Iyer','Nair','Rao','Reddy','Pillai','Menon','Shetty','Kumar','Das','Bose',
              'Sen','Gupta','Shah','Patel','Joshi','Kulkarni','Desai','Mehta','Verma','Singh',
              'Khan','Ali','Fernandes','Dsouza','Thomas','George','Varghese','Mathew','Jacob','Paul',
              'Krishnan','Subramanian','Natarajan','Raman','Venkat','Balaji','Murthy','Prasad','Naidu','Chettiar'])
         [1 + (g / 40) % 40] END,
       'e' || g || '@perf.test', 'employee', m.id
FROM tenants t
CROSS JOIN generate_series(201, {EMPLOYEES}) g
JOIN employees m ON m.tenant_id = t.id AND m.public_id = 'P-' || (1 + g % 200)
WHERE t.public_id = 'T-DEMO';

-- {REQUESTS_PER_EMPLOYEE} requests per person, 14 days apart (never overlapping), 1-3 days long.
-- About 10% pending, 60% approved, 20% rejected, 10% cancelled.
INSERT INTO leave_requests (tenant_id, public_id, employee_id, leave_type_id, start_date,
                            end_date, reason, status, days, decided_by, decision_note)
SELECT e.tenant_id, 'LP-' || e.id || '-' || i, e.id, lt.id,
       DATE '2026-01-05' + (i * 14 + e.id % 5)::int,
       DATE '2026-01-05' + (i * 14 + e.id % 5 + (e.id + i) % 3)::int,
       'Seeded leave for performance tests',
       s.status, (e.id + i) % 3 + 1,
       CASE WHEN s.status IN ('approved', 'rejected') THEN e.manager_id END,
       CASE WHEN s.status = 'rejected' THEN 'Seeded rejection' END
FROM employees e
CROSS JOIN generate_series(0, {REQUESTS_PER_EMPLOYEE - 1}) i
JOIN leave_types lt ON lt.code = 'ANNUAL'
CROSS JOIN LATERAL (SELECT CASE (e.id * 7 + i) % 10
                             WHEN 0 THEN 'pending' WHEN 1 THEN 'cancelled'
                             WHEN 2 THEN 'rejected' WHEN 3 THEN 'rejected'
                             ELSE 'approved' END AS status) s
WHERE e.public_id LIKE 'P-%';

ANALYZE employees;
ANALYZE leave_requests;
"""

T = "(SELECT id FROM tenants WHERE public_id = 'T-DEMO')"


def person(public_id: str) -> str:
    """Look a person up the way the app does: tenant + public id (uses the unique index)."""
    return f"(SELECT id FROM employees WHERE tenant_id = {T} AND public_id = '{public_id}')"


QUERIES = {
    "Q1 Manager's pending queue (manager P-1, oldest start first)": f"""
        SELECT r.public_id, e.name, r.start_date, r.end_date
        FROM leave_requests r JOIN employees e ON e.id = r.employee_id
        WHERE e.manager_id = {person("P-1")}
          AND r.status = 'pending'
        ORDER BY r.start_date, r.id
        LIMIT 20""",
    "Q2 An employee's history (P-5000, newest first)": f"""
        SELECT public_id, start_date, end_date, status
        FROM leave_requests
        WHERE employee_id = {person("P-5000")}
        ORDER BY start_date DESC, id DESC
        LIMIT 20""",
    "Q3 Employee name search (name ILIKE '%aswam%')": f"""
        SELECT public_id, name FROM employees WHERE tenant_id = {T} AND name ILIKE '%aswam%'""",
}

OFFSET_SQL = """
        SELECT public_id, start_date FROM leave_requests
        ORDER BY start_date, id
        OFFSET 50000 LIMIT 20"""
# A real keyset cursor is the (start_date, id) of the last row on the previous page,
# which the client already has; main() fills it in before explaining.
KEYSET_SQL = """
        SELECT public_id, start_date FROM leave_requests
        WHERE (start_date, id) > (DATE '{start_date}', {id})
        ORDER BY start_date, id
        LIMIT 20"""


def explain(conn: psycopg.Connection, sql: str, *, drop: tuple[str, ...] = ()) -> str:
    """EXPLAIN inside a transaction that is always rolled back, after running `drop`."""
    with conn.transaction(force_rollback=True):
        for statement in drop:
            conn.execute(statement)
        rows = conn.execute("EXPLAIN (ANALYZE, BUFFERS, COSTS OFF) " + sql).fetchall()
    return "\n".join(row[0] for row in rows)


def main() -> None:
    url = _Settings().test_migration_database_url.get_secret_value()  # type: ignore[call-arg]
    database = urlsplit(url).path.lstrip("/")
    if not database.endswith("_test"):
        raise SystemExit(f"Refusing to seed {database!r}: the database name must end in _test")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    libpq = url.replace("postgresql+psycopg://", "postgresql://", 1)
    out: list[str] = []

    print("migrating the test database to 0002 (no query indexes) ...")
    command.upgrade(config, "head")
    command.downgrade(config, "0002")
    with psycopg.connect(libpq, autocommit=True) as conn:
        print(f"seeding {EMPLOYEES} employees and {EMPLOYEES * REQUESTS_PER_EMPLOYEE} requests ...")
        conn.execute(SEED_SQL)
        count = conn.execute("SELECT count(*) FROM leave_requests").fetchone()
        pending = conn.execute(
            "SELECT count(*) FROM leave_requests WHERE status = 'pending'"
        ).fetchone()
        out.append(
            f"Seeded: {count[0] if count else 0} leave requests ({pending[0] if pending else 0} pending), "
            f"{EMPLOYEES} employees.\n"
        )
        cursor = conn.execute(
            "SELECT start_date, id FROM leave_requests ORDER BY start_date, id OFFSET 49999 LIMIT 1"
        ).fetchone()
        assert cursor is not None
        pagination = {
            "P1 OFFSET pagination: page 2,501 of the request list (OFFSET 50000)": OFFSET_SQL,
            "P2 Keyset pagination: the same page, after the last row of page 2,500": (
                KEYSET_SQL.format(start_date=cursor[0], id=cursor[1])
            ),
        }
        no_index = (
            "DROP INDEX IF EXISTS ix_leave_requests_employee_id",
            "ALTER TABLE leave_requests DROP CONSTRAINT leave_requests_no_overlap",
        )
        print("capturing BEFORE plans ...")
        for title, sql in QUERIES.items():
            out.append(f"===== BEFORE (no index)  {title}\n{explain(conn, sql, drop=no_index)}\n")
        for title in list(QUERIES)[:2]:
            out.append(
                f"===== BEFORE (Part A indexes only)  {title}\n{explain(conn, QUERIES[title])}\n"
            )
        for title, sql in pagination.items():
            out.append(f"===== BEFORE  {title}\n{explain(conn, sql)}\n")

    print("migrating to head (0003 adds the query indexes) ...")
    command.upgrade(config, "head")
    with psycopg.connect(libpq, autocommit=True) as conn:
        conn.execute("ANALYZE employees; ANALYZE leave_requests;")
        print("capturing AFTER plans ...")
        for title, sql in {**QUERIES, **pagination}.items():
            out.append(f"===== AFTER   {title}\n{explain(conn, sql)}\n")

    OUTPUT.write_text("\n".join(out))
    print(f"done: plans written to {OUTPUT}")


if __name__ == "__main__":
    main()
