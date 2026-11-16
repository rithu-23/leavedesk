"""Query indexes proven in PERF.md (SCHEMA.md 5.2, SPEC DB-31).

Drafted with autogenerate, then reviewed and reordered by hand:
- pg_trgm must exist before the trigram index (autogenerate cannot know that);
- the history index is created BEFORE the old single-column index on employee_id is
  dropped, so the foreign key is never left without an index, even mid-migration.

On a large live table these would be CREATE INDEX CONCURRENTLY in a non-transactional
revision, so writes are not blocked while they build (SCHEMA.md 5.2).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Trusted extension: the database owner (migrator) may create it.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # Employee name search: name ILIKE '%text%' (a leading wildcard defeats a B-tree).
    op.create_index(
        "ix_employees_name_trgm",
        "employees",
        ["name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )

    # An employee's history, newest first: equality column, then the sort, then the
    # keyset tie-breaker. Also covers the employee_id foreign key...
    op.create_index(
        "ix_leave_requests_history",
        "leave_requests",
        ["employee_id", sa.literal_column("start_date DESC"), sa.literal_column("id DESC")],
        unique=False,
    )
    # ...so the narrower index is now redundant: every extra index slows every write.
    op.drop_index("ix_leave_requests_employee_id", table_name="leave_requests")

    # GET /leave-requests default order (start_date, then id): lets keyset pagination
    # jump straight to the next page instead of counting past OFFSET rows.
    op.create_index(
        "ix_leave_requests_start_date_id", "leave_requests", ["start_date", "id"], unique=False
    )

    # Manager's pending queue: a partial index holds only the pending rows.
    op.create_index(
        "ix_leave_requests_pending",
        "leave_requests",
        ["employee_id", "start_date", "id"],
        unique=False,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("ix_leave_requests_start_date_id", table_name="leave_requests")
    op.drop_index(
        "ix_leave_requests_pending",
        table_name="leave_requests",
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "ix_leave_requests_employee_id", "leave_requests", ["employee_id"], unique=False
    )
    op.drop_index("ix_leave_requests_history", table_name="leave_requests")
    op.drop_index(
        "ix_employees_name_trgm",
        table_name="employees",
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
