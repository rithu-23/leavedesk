"""Login accounts in PostgreSQL (SCHEMA.md 4.4), behind the same interface as UserStore.

Why synchronous, when the rest of the storage is async: login is CPU-bound
(Argon2id is deliberately slow), so the route already runs the whole check in
FastAPI's thread pool. The account lookup runs there too, on a small sync
connection pool, so the event loop is never blocked. The unchanged Day 2 test
for API-28 also calls find_by_email() without await, which this keeps working.

Raw SQL, always through text() with bound parameters (never string formatting).
"""

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
                    "SELECT e.public_id, e.email, u.password_hash "
                    "FROM users u JOIN employees e ON e.id = u.employee_id "
                    "WHERE e.tenant_id = :tenant_id AND lower(e.email) = lower(:email)"
                ),
                {"tenant_id": self._tenant_id, "email": email.strip()},
            ).first()
        if row is None:
            return None
        return UserAccount(employee_id=row[0], email=row[1], password_hash=row[2])

    def dispose(self) -> None:
        """Close the pool's connections (called when the app shuts down)."""
        self._engine.dispose()
