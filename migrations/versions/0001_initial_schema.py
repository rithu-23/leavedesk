"""Initial schema: tables 4.1-4.10 of SCHEMA.md, constraints, FK indexes and seed rows.

The table and index commands were drafted with `alembic revision --autogenerate`
from leavedesk/db/models.py, then reviewed. Everything below the "Not expressible
in the ORM" marker was written by hand with op.execute (SCHEMA.md P6):
- btree_gist + the EXCLUDE constraint that blocks overlapping leave (4.6)
- append-only triggers on leave_ledger and audit_log (4.8, 4.9)
- taking UPDATE/DELETE on those two tables away from the app role (6)
- seed rows: tenant T-DEMO, department Engineering, the three leave types (4.5)

Revision ID: 0001
Revises:
Create Date: 2026-11-16 08:17:01.196152
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


APP_ROLE = "leavedesk_app"  # created by docker/postgres-init/01-roles.sh (SCHEMA.md 6)


def upgrade() -> None:
    # btree_gist lets one GiST index mix plain "=" columns with the range "&&" operator.
    # It is a trusted extension, so the database owner (the migrator) may create it.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_table(
        "leave_types",
        sa.Column("id", sa.SmallInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("default_entitlement", sa.Numeric(precision=5, scale=1), nullable=False),
        sa.Column("max_days_per_request", sa.Numeric(precision=5, scale=1), nullable=True),
        sa.CheckConstraint("code ~ '^[A-Z_]{2,20}$'", name=op.f("ck_leave_types_code_format")),
        sa.CheckConstraint(
            "default_entitlement >= 0", name=op.f("ck_leave_types_entitlement_positive")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leave_types")),
        sa.UniqueConstraint("code", name=op.f("uq_leave_types_code")),
    )
    op.create_table(
        "tenants",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 200", name=op.f("ck_tenants_name_length")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
        sa.UniqueConstraint("public_id", name=op.f("uq_tenants_public_id")),
    )
    op.create_table(
        "departments",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 100", name=op.f("ck_departments_name_length")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_departments_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_departments")),
        sa.UniqueConstraint("tenant_id", "name", name=op.f("uq_departments_tenant_id_name")),
    )
    op.create_table(
        "employees",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column("department_id", sa.BigInteger(), nullable=True),
        sa.Column("manager_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('employee', 'manager')", name=op.f("ck_employees_role_values")
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 100", name=op.f("ck_employees_name_length")
        ),
        sa.CheckConstraint("manager_id <> id", name=op.f("ck_employees_not_own_manager")),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            name=op.f("fk_employees_department_id_departments"),
        ),
        sa.ForeignKeyConstraint(
            ["manager_id"], ["employees.id"], name=op.f("fk_employees_manager_id_employees")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_employees_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_employees")),
        sa.UniqueConstraint(
            "tenant_id", "public_id", name=op.f("uq_employees_tenant_id_public_id")
        ),
    )
    op.create_index(
        op.f("ix_employees_department_id"), "employees", ["department_id"], unique=False
    )
    op.create_index(op.f("ix_employees_manager_id"), "employees", ["manager_id"], unique=False)
    op.create_index(
        "uq_employees_tenant_id_lower_email",
        "employees",
        ["tenant_id", sa.literal_column("lower(email)")],
        unique=True,
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("actor_employee_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=True),
        sa.Column("entity_public_id", sa.Text(), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_employee_id"],
            ["employees.id"],
            name=op.f("fk_audit_log_actor_employee_id_employees"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_audit_log_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index(
        op.f("ix_audit_log_actor_employee_id"), "audit_log", ["actor_employee_id"], unique=False
    )
    op.create_index(op.f("ix_audit_log_tenant_id"), "audit_log", ["tenant_id"], unique=False)
    op.create_table(
        "leave_balances",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("employee_id", sa.BigInteger(), nullable=False),
        sa.Column("leave_type_id", sa.SmallInteger(), nullable=False),
        sa.Column("entitlement", sa.Numeric(precision=5, scale=1), nullable=False),
        sa.Column(
            "used", sa.Numeric(precision=5, scale=1), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "pending", sa.Numeric(precision=5, scale=1), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint(
            "entitlement >= 0 AND used >= 0 AND pending >= 0",
            name=op.f("ck_leave_balances_amounts_positive"),
        ),
        sa.CheckConstraint(
            "used + pending <= entitlement", name=op.f("ck_leave_balances_within_entitlement")
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], name=op.f("fk_leave_balances_employee_id_employees")
        ),
        sa.ForeignKeyConstraint(
            ["leave_type_id"],
            ["leave_types.id"],
            name=op.f("fk_leave_balances_leave_type_id_leave_types"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_leave_balances_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leave_balances")),
        sa.UniqueConstraint(
            "employee_id", "leave_type_id", name=op.f("uq_leave_balances_employee_id_leave_type_id")
        ),
    )
    op.create_index(
        op.f("ix_leave_balances_leave_type_id"), "leave_balances", ["leave_type_id"], unique=False
    )
    op.create_index(
        op.f("ix_leave_balances_tenant_id"), "leave_balances", ["tenant_id"], unique=False
    )
    op.create_table(
        "leave_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column("employee_id", sa.BigInteger(), nullable=False),
        sa.Column("leave_type_id", sa.SmallInteger(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("half_day", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("days", sa.Numeric(precision=5, scale=1), nullable=False),
        sa.Column("decided_by", sa.BigInteger(), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint(
            "status <> 'rejected' OR decision_note IS NOT NULL",
            name=op.f("ck_leave_requests_rejection_has_note"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'cancelled')",
            name=op.f("ck_leave_requests_status_values"),
        ),
        sa.CheckConstraint(
            "NOT half_day OR start_date = end_date",
            name=op.f("ck_leave_requests_half_day_single_date"),
        ),
        sa.CheckConstraint(
            "char_length(reason) BETWEEN 10 AND 500", name=op.f("ck_leave_requests_reason_length")
        ),
        sa.CheckConstraint(
            "days >= 0.5 AND days * 2 = trunc(days * 2)",
            name=op.f("ck_leave_requests_days_half_steps"),
        ),
        sa.CheckConstraint("end_date >= start_date", name=op.f("ck_leave_requests_dates")),
        sa.ForeignKeyConstraint(
            ["decided_by"], ["employees.id"], name=op.f("fk_leave_requests_decided_by_employees")
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], name=op.f("fk_leave_requests_employee_id_employees")
        ),
        sa.ForeignKeyConstraint(
            ["leave_type_id"],
            ["leave_types.id"],
            name=op.f("fk_leave_requests_leave_type_id_leave_types"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_leave_requests_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leave_requests")),
        sa.UniqueConstraint(
            "tenant_id", "public_id", name=op.f("uq_leave_requests_tenant_id_public_id")
        ),
    )
    op.create_index(
        op.f("ix_leave_requests_decided_by"), "leave_requests", ["decided_by"], unique=False
    )
    op.create_index(
        op.f("ix_leave_requests_employee_id"), "leave_requests", ["employee_id"], unique=False
    )
    op.create_index(
        op.f("ix_leave_requests_leave_type_id"), "leave_requests", ["leave_type_id"], unique=False
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("public_id", sa.Text(), nullable=False),
        sa.Column("recipient_id", sa.BigInteger(), nullable=False),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event IN ('submitted', 'approved', 'rejected', 'cancelled')",
            name=op.f("ck_notifications_event_values"),
        ),
        sa.ForeignKeyConstraint(
            ["recipient_id"], ["employees.id"], name=op.f("fk_notifications_recipient_id_employees")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_notifications_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        sa.UniqueConstraint(
            "tenant_id", "public_id", name=op.f("uq_notifications_tenant_id_public_id")
        ),
    )
    op.create_index(
        op.f("ix_notifications_recipient_id"), "notifications", ["recipient_id"], unique=False
    )
    op.create_index(
        "ix_notifications_unread",
        "notifications",
        ["tenant_id", "recipient_id", sa.literal_column("created_at DESC")],
        unique=False,
        postgresql_where=sa.text("read_at IS NULL"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("employee_id", sa.BigInteger(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("failed_login_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "password_hash LIKE '$argon2id$%%'", name=op.f("ck_users_argon2id_hash")
        ),
        sa.CheckConstraint(
            "failed_login_count >= 0", name=op.f("ck_users_failed_login_count_positive")
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], name=op.f("fk_users_employee_id_employees")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_users_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("employee_id", name=op.f("uq_users_employee_id")),
    )
    op.create_index(op.f("ix_users_tenant_id"), "users", ["tenant_id"], unique=False)
    op.create_table(
        "leave_ledger",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("employee_id", sa.BigInteger(), nullable=False),
        sa.Column("leave_type_id", sa.SmallInteger(), nullable=False),
        sa.Column("leave_request_id", sa.BigInteger(), nullable=True),
        sa.Column("entry_type", sa.Text(), nullable=False),
        sa.Column(
            "entitlement_delta",
            sa.Numeric(precision=5, scale=1),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "used_delta",
            sa.Numeric(precision=5, scale=1),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "pending_delta",
            sa.Numeric(precision=5, scale=1),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "entry_type IN ('grant', 'reserve', 'confirm', 'release')",
            name=op.f("ck_leave_ledger_entry_type_values"),
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], name=op.f("fk_leave_ledger_employee_id_employees")
        ),
        sa.ForeignKeyConstraint(
            ["leave_request_id"],
            ["leave_requests.id"],
            name=op.f("fk_leave_ledger_leave_request_id_leave_requests"),
        ),
        sa.ForeignKeyConstraint(
            ["leave_type_id"],
            ["leave_types.id"],
            name=op.f("fk_leave_ledger_leave_type_id_leave_types"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_leave_ledger_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leave_ledger")),
    )
    op.create_index(
        op.f("ix_leave_ledger_employee_id"), "leave_ledger", ["employee_id"], unique=False
    )
    op.create_index(
        op.f("ix_leave_ledger_leave_request_id"), "leave_ledger", ["leave_request_id"], unique=False
    )
    op.create_index(
        op.f("ix_leave_ledger_leave_type_id"), "leave_ledger", ["leave_type_id"], unique=False
    )
    op.create_index(op.f("ix_leave_ledger_tenant_id"), "leave_ledger", ["tenant_id"], unique=False)

    # ---------- Not expressible in the ORM (written by hand) ----------

    # SCHEMA.md 4.6 / SPEC BR-9: no two pending or approved requests of the same employee
    # may overlap. '[]' includes both end dates. Raises SQLSTATE 23P01 on violation.
    op.execute(
        """
        ALTER TABLE leave_requests ADD CONSTRAINT leave_requests_no_overlap
          EXCLUDE USING gist (
            tenant_id   WITH =,
            employee_id WITH =,
            daterange(start_date, end_date, '[]') WITH &&
          ) WHERE (status IN ('pending', 'approved'))
        """
    )

    # SCHEMA.md 4.8 / 4.9: history is never rewritten. The trigger blocks UPDATE and DELETE
    # for every role, including the migrator; the REVOKE below is the second layer.
    op.execute(
        """
        CREATE FUNCTION forbid_change() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION '% is append-only: % is not allowed', TG_TABLE_NAME, TG_OP
            USING ERRCODE = 'restrict_violation';
        END;
        $$
        """
    )
    for table in ("leave_ledger", "audit_log"):
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION forbid_change()"
        )

    # SCHEMA.md 6: default privileges gave the app role full DML on every new table;
    # the append-only tables keep SELECT and INSERT only. Skipped if the role does not
    # exist (for example a developer database created without the init script).
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            REVOKE UPDATE, DELETE ON leave_ledger, audit_log FROM {APP_ROLE};
          END IF;
        END
        $$
        """
    )

    # Seed rows (SCHEMA.md 4.5, P2). Values match leavedesk/domain/balance.py and policies.py.
    op.execute("INSERT INTO tenants (public_id, name) VALUES ('T-DEMO', 'LeaveDesk Demo')")
    op.execute(
        "INSERT INTO departments (tenant_id, name) "
        "SELECT id, 'Engineering' FROM tenants WHERE public_id = 'T-DEMO'"
    )
    op.execute(
        """
        INSERT INTO leave_types (code, name, default_entitlement, max_days_per_request) VALUES
          ('ANNUAL', 'Annual leave', 18, NULL),
          ('SICK',   'Sick leave',   12, NULL),
          ('CASUAL', 'Casual leave',  6, 2)
        """
    )


def downgrade() -> None:
    # Dropping a table also drops its triggers and the EXCLUDE constraint.
    op.drop_index(op.f("ix_leave_ledger_tenant_id"), table_name="leave_ledger")
    op.drop_index(op.f("ix_leave_ledger_leave_type_id"), table_name="leave_ledger")
    op.drop_index(op.f("ix_leave_ledger_leave_request_id"), table_name="leave_ledger")
    op.drop_index(op.f("ix_leave_ledger_employee_id"), table_name="leave_ledger")
    op.drop_table("leave_ledger")
    op.drop_index(op.f("ix_users_tenant_id"), table_name="users")
    op.drop_table("users")
    op.drop_index(
        "ix_notifications_unread",
        table_name="notifications",
        postgresql_where=sa.text("read_at IS NULL"),
    )
    op.drop_index(op.f("ix_notifications_recipient_id"), table_name="notifications")
    op.drop_table("notifications")
    op.drop_index(op.f("ix_leave_requests_leave_type_id"), table_name="leave_requests")
    op.drop_index(op.f("ix_leave_requests_employee_id"), table_name="leave_requests")
    op.drop_index(op.f("ix_leave_requests_decided_by"), table_name="leave_requests")
    op.drop_table("leave_requests")
    op.drop_index(op.f("ix_leave_balances_tenant_id"), table_name="leave_balances")
    op.drop_index(op.f("ix_leave_balances_leave_type_id"), table_name="leave_balances")
    op.drop_table("leave_balances")
    op.drop_index(op.f("ix_audit_log_tenant_id"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_actor_employee_id"), table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("uq_employees_tenant_id_lower_email", table_name="employees")
    op.drop_index(op.f("ix_employees_manager_id"), table_name="employees")
    op.drop_index(op.f("ix_employees_department_id"), table_name="employees")
    op.drop_table("employees")
    op.drop_table("departments")
    op.drop_table("tenants")
    op.drop_table("leave_types")
    op.execute("DROP FUNCTION IF EXISTS forbid_change()")
    op.execute("DROP EXTENSION IF EXISTS btree_gist")
