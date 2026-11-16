"""SQLAlchemy 2 models for LeaveDesk (Capstone 3). SCHEMA.md is the specification.

Conventions (SCHEMA.md sections 1-2):
- Every table has `id`, an identity primary key (bigint; smallint for leave_types).
- Rows the API exposes also have `public_id` (E-ANA, LR-1a2b3c4d), unique per tenant.
- Every business table has `tenant_id`; day counts are numeric(5,1); timestamps are timestamptz.
- Classes end in `Row` so they are never confused with the domain's Pydantic models.
- Relationships use lazy="raise": touching one that was not loaded explicitly
  (selectinload / joinedload) raises at once, so an N+1 query cannot slip in unnoticed.

What the ORM cannot express is written only in the Alembic revision with op.execute:
the EXCLUDE constraint, the expression index on lower(email), the append-only
triggers and the privilege changes (SCHEMA.md 4.6, 4.3, 4.8, 6).
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from leavedesk.db.base import Base

DAYS = Numeric(5, 1, asdecimal=True)  # SCHEMA.md 2.3: exact half days, up to 9999.9
TIMESTAMP = DateTime(timezone=True)  # SCHEMA.md 2.4: timestamptz


def _id() -> Mapped[int]:
    return mapped_column(BigInteger, Identity(always=True), primary_key=True)


def _created_at() -> Mapped[datetime]:
    return mapped_column(TIMESTAMP, nullable=False, server_default=func.now())


class TenantRow(Base):
    __tablename__ = "tenants"
    __table_args__ = (CheckConstraint("char_length(name) BETWEEN 1 AND 200", name="name_length"),)

    id: Mapped[int] = _id()
    public_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()


class DepartmentRow(Base):
    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name"),  # also covers the tenant_id foreign key
        CheckConstraint("char_length(name) BETWEEN 1 AND 100", name="name_length"),
    )

    id: Mapped[int] = _id()
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()


class EmployeeRow(Base):
    __tablename__ = "employees"
    __table_args__ = (
        UniqueConstraint("tenant_id", "public_id"),  # also covers the tenant_id foreign key
        CheckConstraint("char_length(name) BETWEEN 1 AND 100", name="name_length"),
        CheckConstraint("role IN ('employee', 'manager')", name="role_values"),
        CheckConstraint("manager_id <> id", name="not_own_manager"),
        # Case-insensitive email per tenant (SCHEMA.md 4.3); an expression index, so the
        # revision creates it with op.execute. Declared here so Alembic knows it exists.
        Index("uq_employees_tenant_id_lower_email", "tenant_id", text("lower(email)"), unique=True),
        # name ILIKE '%text%': a B-tree cannot help with a leading wildcard; trigrams can.
        Index(
            "ix_employees_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = _id()
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    public_id: Mapped[str] = mapped_column(Text, nullable=False)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), index=True)
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()

    manager: Mapped["EmployeeRow | None"] = relationship(remote_side=[id], lazy="raise")


class UserRow(Base):
    """A login account: one per employee. The email lives on employees (SCHEMA.md 4.4)."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("password_hash LIKE '$argon2id$%'", name="argon2id_hash"),
        CheckConstraint("failed_login_count >= 0", name="failed_login_count_positive"),
    )

    id: Mapped[int] = _id()
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"), nullable=False, unique=True
    )
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    failed_login_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    locked_until: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    last_login_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    created_at: Mapped[datetime] = _created_at()

    employee: Mapped[EmployeeRow] = relationship(lazy="raise")


class LeaveTypeRow(Base):
    """Lookup table shared by all tenants (SCHEMA.md 2.2 and 4.5)."""

    __tablename__ = "leave_types"
    __table_args__ = (
        CheckConstraint("code ~ '^[A-Z_]{2,20}$'", name="code_format"),
        CheckConstraint("default_entitlement >= 0", name="entitlement_positive"),
    )

    id: Mapped[int] = mapped_column(SmallInteger, Identity(always=True), primary_key=True)
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    default_entitlement: Mapped[Decimal] = mapped_column(DAYS, nullable=False)
    max_days_per_request: Mapped[Decimal | None] = mapped_column(DAYS)


class LeaveRequestRow(Base):
    __tablename__ = "leave_requests"
    __table_args__ = (
        UniqueConstraint("tenant_id", "public_id"),  # also covers the tenant_id foreign key
        CheckConstraint("end_date >= start_date", name="dates"),
        CheckConstraint("NOT half_day OR start_date = end_date", name="half_day_single_date"),
        CheckConstraint("char_length(reason) BETWEEN 10 AND 500", name="reason_length"),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'cancelled')", name="status_values"
        ),
        CheckConstraint("days >= 0.5 AND days * 2 = trunc(days * 2)", name="days_half_steps"),
        CheckConstraint(
            "status <> 'rejected' OR decision_note IS NOT NULL", name="rejection_has_note"
        ),
        # Query indexes (SCHEMA.md 5.2, proven in PERF.md):
        # manager's pending queue: only pending rows, equality column first, then the sort.
        Index(
            "ix_leave_requests_pending",
            "employee_id",
            "start_date",
            "id",
            postgresql_where=text("status = 'pending'"),
        ),
        # the list endpoint's default order; makes keyset pagination a short index range.
        Index("ix_leave_requests_start_date_id", "start_date", "id"),
        # an employee's history, newest first, with id as the keyset tie-breaker.
        Index(
            "ix_leave_requests_history",
            "employee_id",
            text("start_date DESC"),
            text("id DESC"),
        ),
        # The EXCLUDE constraint (no overlapping pending/approved leave) is added in the
        # revision with op.execute: SCHEMA.md 4.6.
    )

    id: Mapped[int] = _id()
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    public_id: Mapped[str] = mapped_column(Text, nullable=False)
    # No single-column index: ix_leave_requests_history starts with employee_id, so it
    # also covers this foreign key (SCHEMA.md 5.2, revision 0003).
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    leave_type_id: Mapped[int] = mapped_column(
        ForeignKey("leave_types.id"), nullable=False, index=True
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    half_day: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    days: Mapped[Decimal] = mapped_column(DAYS, nullable=False)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), index=True)
    decision_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    # Optimistic locking (SCHEMA.md 7): every UPDATE adds "AND version = <value read>" and
    # bumps it; no row matched -> StaleDataError. Must reference the column object itself:
    # a plain string "version" is accepted silently and does nothing.
    __mapper_args__ = {"version_id_col": version}

    employee: Mapped[EmployeeRow] = relationship(foreign_keys=[employee_id], lazy="raise")
    leave_type: Mapped[LeaveTypeRow] = relationship(lazy="raise")
    decider: Mapped[EmployeeRow | None] = relationship(foreign_keys=[decided_by], lazy="raise")


class LeaveBalanceRow(Base):
    __tablename__ = "leave_balances"
    __table_args__ = (
        UniqueConstraint("employee_id", "leave_type_id"),  # also covers the employee_id FK
        CheckConstraint("entitlement >= 0 AND used >= 0 AND pending >= 0", name="amounts_positive"),
        CheckConstraint("used + pending <= entitlement", name="within_entitlement"),
    )

    id: Mapped[int] = _id()
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    leave_type_id: Mapped[int] = mapped_column(
        ForeignKey("leave_types.id"), nullable=False, index=True
    )
    entitlement: Mapped[Decimal] = mapped_column(DAYS, nullable=False)
    used: Mapped[Decimal] = mapped_column(DAYS, nullable=False, server_default=text("0"))
    pending: Mapped[Decimal] = mapped_column(DAYS, nullable=False, server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    # Optimistic locking (SCHEMA.md 7): every UPDATE adds "AND version = <value read>" and
    # bumps it; no row matched -> StaleDataError. Must reference the column object itself:
    # a plain string "version" is accepted silently and does nothing.
    __mapper_args__ = {"version_id_col": version}

    leave_type: Mapped[LeaveTypeRow] = relationship(lazy="raise")


class LeaveLedgerRow(Base):
    """Append-only record of every balance movement (SCHEMA.md 2.6 and 4.8)."""

    __tablename__ = "leave_ledger"
    __table_args__ = (
        CheckConstraint(
            "entry_type IN ('grant', 'reserve', 'confirm', 'release')", name="entry_type_values"
        ),
    )

    id: Mapped[int] = _id()
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    leave_type_id: Mapped[int] = mapped_column(
        ForeignKey("leave_types.id"), nullable=False, index=True
    )
    leave_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("leave_requests.id"), index=True
    )
    entry_type: Mapped[str] = mapped_column(Text, nullable=False)
    entitlement_delta: Mapped[Decimal] = mapped_column(
        DAYS, nullable=False, server_default=text("0")
    )
    used_delta: Mapped[Decimal] = mapped_column(DAYS, nullable=False, server_default=text("0"))
    pending_delta: Mapped[Decimal] = mapped_column(DAYS, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = _created_at()


class AuditLogRow(Base):
    """Append-only audit trail, written in the same transaction as the change (SCHEMA.md 4.9)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = _id()
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    actor_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), index=True)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(Text)
    entity_public_id: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = _created_at()


class NotificationRow(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("tenant_id", "public_id"),  # also covers the tenant_id foreign key
        CheckConstraint(
            "event IN ('submitted', 'approved', 'rejected', 'cancelled')", name="event_values"
        ),
        # Partial index: only unread rows, per recipient, newest first (SCHEMA.md 4.10).
        Index(
            "ix_notifications_unread",
            "tenant_id",
            "recipient_id",
            text("created_at DESC"),
            postgresql_where=text("read_at IS NULL"),
        ),
    )

    id: Mapped[int] = _id()
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    public_id: Mapped[str] = mapped_column(Text, nullable=False)
    recipient_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"), nullable=False, index=True
    )
    event: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    read_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    created_at: Mapped[datetime] = _created_at()

    recipient: Mapped[EmployeeRow] = relationship(lazy="raise")


class NotificationOutboxRow(Base):
    """One row per notification still to be sent (transactional outbox, SCHEMA.md 4.11).

    Inserted in the same transaction as the leave action, so a rolled-back action
    leaves no row. Senders claim rows with FOR UPDATE SKIP LOCKED (leavedesk/db/outbox.py).
    """

    __tablename__ = "notification_outbox"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'sent', 'failed')", name="status_values"),
        CheckConstraint("attempts >= 0", name="attempts_positive"),
        # Only rows still waiting: the index senders scan stays small forever.
        Index(
            "ix_outbox_pending",
            "available_at",
            "id",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[int] = _id()
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    notification_id: Mapped[int] = mapped_column(
        ForeignKey("notifications.id"), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    available_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()

    notification: Mapped[NotificationRow] = relationship(lazy="raise")


class IdempotencyKeyRow(Base):
    """The first response to a submit sent with an Idempotency-Key (SCHEMA.md 4.12).

    Saved in the same transaction as the new leave request, so a failed submit stores
    nothing and can be retried with the same key (SPEC BR-11).
    """

    __tablename__ = "idempotency_keys"
    __table_args__ = (
        # Keys are scoped to one employee; this UNIQUE does not start with employee_id,
        # so that foreign key gets its own index below (SCHEMA.md 5.1).
        UniqueConstraint("tenant_id", "employee_id", "key"),
        CheckConstraint("char_length(key) BETWEEN 1 AND 255", name="key_length"),
    )

    id: Mapped[int] = _id()
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    leave_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("leave_requests.id"), index=True
    )
    response_status: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = _created_at()
