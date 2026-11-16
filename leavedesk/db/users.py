"""Login accounts in PostgreSQL (SCHEMA.md 4.4), behind the same interface as UserStore.

Why synchronous, when the rest of the storage is async: login is CPU-bound
(Argon2id is deliberately slow), so the route already runs the whole check in
FastAPI's thread pool. The account lookup runs there too, on a small sync
connection pool, so the event loop is never blocked. The unchanged Day 2 test
for API-28 also calls find_by_email() without await, which this keeps working.

Raw SQL, always through text() with bound parameters (never string formatting).
"""

from datetime import datetime, timedelta

from sqlalchemy import Engine, create_engine, text

from leavedesk.api.users import UserAccount


class PostgresUserStore:
    """Finds and adds login accounts for one tenant."""

    def __init__(self, database_url: str, tenant_id: int) -> None:
        self._tenant_id = tenant_id
        self._engine: Engine = create_engine(
            database_url, pool_size=2, max_overflow=2, pool_pre_ping=True
        )

    def add(self, account: UserAccount) -> None:
        """Create the login for an existing employee; does nothing if it already exists."""
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (tenant_id, employee_id, password_hash) "
                    "SELECT e.tenant_id, e.id, :password_hash FROM employees e "
                    "WHERE e.tenant_id = :tenant_id AND e.public_id = :employee_id "
                    "ON CONFLICT (employee_id) DO NOTHING"
                ),
                {
                    "password_hash": account.password_hash,
                    "tenant_id": self._tenant_id,
                    "employee_id": account.employee_id,
                },
            )

    def find_by_email(self, email: str) -> UserAccount | None:
        """Case-insensitive, like the unique index on lower(email) (SCHEMA.md 4.3)."""
        with self._engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT e.public_id, e.email, u.password_hash, u.failed_login_count, "
                    "u.locked_until "
                    "FROM users u JOIN employees e ON e.id = u.employee_id "
                    "WHERE e.tenant_id = :tenant_id AND lower(e.email) = lower(:email)"
                ),
                {"tenant_id": self._tenant_id, "email": email.strip()},
            ).first()
        if row is None:
            return None
        return UserAccount(
            employee_id=row[0],
            email=row[1],
            password_hash=row[2],
            failed_login_count=row[3],
            locked_until=row[4],
        )

    def record_failed_login(
        self, employee_id: str, *, max_attempts: int, lock_minutes: int, now: datetime
    ) -> bool:
        """One atomic conditional UPDATE, so two wrong passwords at the same moment are
        both counted (no read-then-write race). Writes an audit row when it locks."""
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    "UPDATE users u SET "
                    "  failed_login_count = CASE WHEN u.locked_until <= :now THEN 1 "
                    "                            ELSE u.failed_login_count + 1 END, "
                    "  locked_until = CASE "
                    "    WHEN (CASE WHEN u.locked_until <= :now THEN 1 "
                    "               ELSE u.failed_login_count + 1 END) >= :max_attempts "
                    "    THEN CAST(:lock_until AS timestamptz) ELSE NULL END "
                    "FROM employees e "
                    "WHERE e.id = u.employee_id AND e.tenant_id = :tenant_id "
                    "  AND e.public_id = :employee_id "
                    "RETURNING u.failed_login_count, u.locked_until, e.id"
                ),
                {
                    "now": now,
                    "max_attempts": max_attempts,
                    "lock_until": now + timedelta(minutes=lock_minutes),
                    "tenant_id": self._tenant_id,
                    "employee_id": employee_id,
                },
            ).first()
            just_locked = row is not None and row[0] == max_attempts and row[1] is not None
            if just_locked:
                assert row is not None
                connection.execute(
                    text(
                        "INSERT INTO audit_log (tenant_id, actor_employee_id, action, "
                        "entity_type, entity_public_id, details) VALUES (:tenant_id, :actor, "
                        "'auth.lockout', 'user', :employee_id, "
                        "jsonb_build_object('failed_attempts', CAST(:attempts AS int)))"
                    ),
                    {
                        "tenant_id": self._tenant_id,
                        "actor": row[2],
                        "employee_id": employee_id,
                        "attempts": row[0],
                    },
                )
        return just_locked

    def record_successful_login(self, employee_id: str, *, now: datetime) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE users u SET failed_login_count = 0, locked_until = NULL, "
                    "last_login_at = :now FROM employees e "
                    "WHERE e.id = u.employee_id AND e.tenant_id = :tenant_id "
                    "AND e.public_id = :employee_id"
                ),
                {"now": now, "tenant_id": self._tenant_id, "employee_id": employee_id},
            )

    def dispose(self) -> None:
        """Close the pool's connections (called when the app shuts down)."""
        self._engine.dispose()
