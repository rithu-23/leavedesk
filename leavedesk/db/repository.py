"""PostgreSQL implementation of LeaveRepository (Capstone 3, SPEC FR-12).

One instance per HTTP request, bound to that request's AsyncSession. The
session's transaction is opened and committed by the API dependency
(leavedesk/api/deps.py), so everything a request does here is saved together
or not at all (SPEC BR-10).

Mapping between the two worlds:
- The domain uses public ids (E-ANA, LR-1a2b3c4d); the database joins on
  internal identity keys. This class translates, and caches lookups for the
  length of the request so the same id is not resolved twice.
- Domain objects are Pydantic models / dataclasses; rows are SQLAlchemy models.
  Rows loaded in this request are kept in small caches so a later save updates
  the same row object, which carries the `version` read earlier. SQLAlchemy then
  adds "AND version = <read value>" to the UPDATE (optimistic locking).

Database errors are translated into domain errors, so the API's error contract
does not change:
- EXCLUDE violation (SQLSTATE 23P01)          -> OverlappingLeaveError (409)
- version mismatch (StaleDataError)           -> ConcurrentUpdateError (409)
Every query goes through select() or text() with bound parameters.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.exc import StaleDataError

from leavedesk.db.models import (
    EmployeeRow,
    IdempotencyKeyRow,
    LeaveBalanceRow,
    LeaveLedgerRow,
    LeaveRequestRow,
    LeaveTypeRow,
    NotificationOutboxRow,
    NotificationRow,
)
from leavedesk.domain.balance import LeaveBalance
from leavedesk.domain.exceptions import (
    ConcurrentUpdateError,
    NotFoundError,
    OverlappingLeaveError,
)
from leavedesk.domain.models import (
    Employee,
    LeaveRequest,
    LeaveStatus,
    LeaveType,
    Notification,
    NotificationEvent,
    Role,
)
from leavedesk.domain.repository import LeaveRepository, StoredResponse

EXCLUSION_VIOLATION = "23P01"


def _days(value: Decimal) -> Decimal:
    """numeric(5,1) always returns one decimal place (3.0); the domain and the API
    write whole days without it ("3", "18") and half days as "14.5".

    Not Decimal.normalize(): that turns 10.0 into 1E+1, which the API would print.
    """
    return value.quantize(Decimal(1)) if value == value.to_integral_value() else value


def _sqlstate(error: IntegrityError) -> str | None:
    return getattr(error.orig, "sqlstate", None)


class PostgresLeaveRepository(LeaveRepository):
    """LeaveRepository backed by PostgreSQL through one AsyncSession."""

    def __init__(self, session: AsyncSession, tenant_id: int) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._employee_pks: dict[str, int] = {}
        self._leave_type_pks: dict[LeaveType, int] = {}
        self._request_rows: dict[str, LeaveRequestRow] = {}
        self._balance_rows: dict[tuple[str, LeaveType], LeaveBalanceRow] = {}
        self._notification_rows: dict[str, NotificationRow] = {}

    # ------------------------------------------------------------ lookups

    async def _employee_pk(self, public_id: str) -> int:
        if public_id not in self._employee_pks:
            pk = await self._session.scalar(
                select(EmployeeRow.id).where(
                    EmployeeRow.tenant_id == self._tenant_id, EmployeeRow.public_id == public_id
                )
            )
            if pk is None:
                raise NotFoundError("Employee", public_id)
            self._employee_pks[public_id] = pk
        return self._employee_pks[public_id]

    async def _leave_type_pk(self, leave_type: LeaveType) -> int:
        if not self._leave_type_pks:  # three rows: load them all once per request
            rows = await self._session.execute(select(LeaveTypeRow.code, LeaveTypeRow.id))
            self._leave_type_pks = {LeaveType(code): pk for code, pk in rows.all()}
        return self._leave_type_pks[leave_type]

    async def _flush(self, entity: str, entity_id: str) -> None:
        """Send pending changes now, so constraint and version errors surface here,
        inside the request, where they can still become the right HTTP error."""
        try:
            await self._session.flush()
        except StaleDataError as error:
            raise ConcurrentUpdateError(entity, entity_id) from error

    # ---------------------------------------------------------- employees

    @staticmethod
    def _to_employee(row: EmployeeRow) -> Employee:
        return Employee(
            id=row.public_id,
            name=row.name,
            email=row.email,
            role=Role(row.role),
            manager_id=row.manager.public_id if row.manager is not None else None,
        )

    def _employee_query(self) -> Any:
        # joinedload: the manager comes back in the same query (no N+1).
        return (
            select(EmployeeRow)
            .options(joinedload(EmployeeRow.manager))
            .where(EmployeeRow.tenant_id == self._tenant_id)
        )

    async def add_employee(self, employee: Employee) -> None:
        manager_pk = await self._employee_pk(employee.manager_id) if employee.manager_id else None
        row = EmployeeRow(
            tenant_id=self._tenant_id,
            public_id=employee.id,
            name=employee.name,
            email=employee.email,
            role=employee.role.value,
            manager_id=manager_pk,
        )
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError as error:
            raise ValueError(f"employee {employee.id} already exists") from error
        self._employee_pks[employee.id] = row.id

    async def get_employee(self, employee_id: str) -> Employee:
        row = await self._session.scalar(
            self._employee_query().where(EmployeeRow.public_id == employee_id)
        )
        if row is None:
            raise NotFoundError("Employee", employee_id)
        self._employee_pks[employee_id] = row.id
        return self._to_employee(row)

    async def list_employees(self) -> list[Employee]:
        rows = await self._session.scalars(self._employee_query().order_by(EmployeeRow.id))
        return [self._to_employee(row) for row in rows.unique()]

    # ----------------------------------------------------- leave requests

    @staticmethod
    def _to_request(row: LeaveRequestRow) -> LeaveRequest:
        return LeaveRequest(
            id=row.public_id,
            employee_id=row.employee.public_id,
            leave_type=LeaveType(row.leave_type.code),
            start_date=row.start_date,
            end_date=row.end_date,
            half_day=row.half_day,
            reason=row.reason,
            status=LeaveStatus(row.status),
            days=_days(row.days),
            created_at=row.created_at,
            decided_by=row.decider.public_id if row.decider is not None else None,
            decision_note=row.decision_note,
            version=row.version,
        )

    def _request_query(self) -> Any:
        # Employee and leave type always exist (inner join); the decider may be NULL (outer join).
        return (
            select(LeaveRequestRow)
            .options(
                joinedload(LeaveRequestRow.employee, innerjoin=True),
                joinedload(LeaveRequestRow.leave_type, innerjoin=True),
                joinedload(LeaveRequestRow.decider),
            )
            .where(LeaveRequestRow.tenant_id == self._tenant_id)
        )

    async def add_request(self, request: LeaveRequest) -> None:
        row = LeaveRequestRow(
            tenant_id=self._tenant_id,
            public_id=request.id,
            employee_id=await self._employee_pk(request.employee_id),
            leave_type_id=await self._leave_type_pk(request.leave_type),
            start_date=request.start_date,
            end_date=request.end_date,
            half_day=request.half_day,
            reason=request.reason,
            status=request.status.value,
            days=request.days,
            created_at=request.created_at,
            decided_by=await self._employee_pk(request.decided_by) if request.decided_by else None,
            decision_note=request.decision_note,
        )
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError as error:
            if _sqlstate(error) == EXCLUSION_VIOLATION:
                # Two overlapping submits raced past the Python check (SPEC DB-7);
                # the EXCLUDE constraint stopped the second one.
                raise OverlappingLeaveError("(a request saved at the same moment)") from error
            raise
        self._request_rows[request.id] = row

    async def _request_row(self, request_id: str, *, lock: bool = False) -> LeaveRequestRow:
        query = self._request_query().where(LeaveRequestRow.public_id == request_id)
        if lock:
            # FOR UPDATE OF leave_requests only: PostgreSQL cannot lock the nullable side
            # of the outer join to the decider, and the other rows need no lock.
            query = query.with_for_update(of=LeaveRequestRow)
        # populate_existing: refresh a row already in this session with what the
        # database holds now (after waiting for the lock), not the earlier copy.
        row = await self._session.scalar(query.execution_options(populate_existing=True))
        if row is None:
            raise NotFoundError("LeaveRequest", request_id)
        self._request_rows[request_id] = row
        return row

    async def get_request(self, request_id: str, *, lock: bool = False) -> LeaveRequest:
        return self._to_request(await self._request_row(request_id, lock=lock))

    async def save_request(self, request: LeaveRequest) -> None:
        row = self._request_rows.get(request.id) or await self._request_row(request.id)
        # Every lookup BEFORE the first change to the row: a lookup is a query, and
        # SQLAlchemy flushes pending changes before a query (autoflush), which would
        # run the version check outside _flush() and skip the error translation.
        decided_by = await self._employee_pk(request.decided_by) if request.decided_by else None
        row.status = request.status.value
        row.decided_by = decided_by
        row.decision_note = request.decision_note
        await self._flush("LeaveRequest", request.id)
        request.version = row.version  # SQLAlchemy bumped it in the UPDATE

    async def list_requests(
        self, employee_id: str | None = None, status: LeaveStatus | None = None
    ) -> list[LeaveRequest]:
        query = self._request_query()
        if employee_id is not None:
            query = query.where(LeaveRequestRow.employee_id == await self._employee_pk(employee_id))
        if status is not None:
            query = query.where(LeaveRequestRow.status == status.value)
        rows = await self._session.scalars(
            query.order_by(LeaveRequestRow.start_date, LeaveRequestRow.id)
        )
        return [self._to_request(row) for row in rows.unique()]

    # ----------------------------------------------------------- balances

    async def _balance_row(
        self, employee_id: str, leave_type: LeaveType, *, lock: bool = False
    ) -> LeaveBalanceRow | None:
        query = select(LeaveBalanceRow).where(
            LeaveBalanceRow.employee_id == await self._employee_pk(employee_id),
            LeaveBalanceRow.leave_type_id == await self._leave_type_pk(leave_type),
        )
        if lock:
            query = query.with_for_update()
        row = await self._session.scalar(query.execution_options(populate_existing=True))
        if row is not None:
            self._balance_rows[(employee_id, leave_type)] = row
        return row

    async def get_balance(
        self, employee_id: str, leave_type: LeaveType, *, lock: bool = False
    ) -> LeaveBalance:
        row = await self._balance_row(employee_id, leave_type, lock=lock)
        if row is None:
            raise NotFoundError("LeaveBalance", f"{employee_id}/{leave_type}")
        return LeaveBalance(
            employee_id=employee_id,
            leave_type=leave_type,
            entitlement=_days(row.entitlement),
            used=_days(row.used),
            pending=_days(row.pending),
        )

    async def save_balance(self, balance: LeaveBalance, *, request_id: str | None = None) -> None:
        """Update the balance row and append the matching ledger row (SCHEMA.md 2.6, 4.8)."""
        key = (balance.employee_id, balance.leave_type)
        row = self._balance_rows.get(key) or await self._balance_row(*key)
        if row is None:
            row = LeaveBalanceRow(
                tenant_id=self._tenant_id,
                employee_id=await self._employee_pk(balance.employee_id),
                leave_type_id=await self._leave_type_pk(balance.leave_type),
                entitlement=Decimal("0"),
                used=Decimal("0"),
                pending=Decimal("0"),
            )
            self._session.add(row)
            self._balance_rows[key] = row

        deltas = {
            "entitlement_delta": balance.entitlement - row.entitlement,
            "used_delta": balance.used - row.used,
            "pending_delta": balance.pending - row.pending,
        }
        if any(deltas.values()):
            request_pk = None
            if request_id is not None:
                request_row = self._request_rows.get(request_id) or await self._request_row(
                    request_id
                )
                request_pk = request_row.id
            self._session.add(
                LeaveLedgerRow(
                    tenant_id=self._tenant_id,
                    employee_id=row.employee_id,
                    leave_type_id=row.leave_type_id,
                    leave_request_id=request_pk,
                    entry_type=_entry_type(**deltas),
                    **deltas,
                )
            )
        row.entitlement, row.used, row.pending = balance.entitlement, balance.used, balance.pending
        await self._flush("LeaveBalance", f"{balance.employee_id}/{balance.leave_type}")

    # ------------------------------------------------------ notifications

    @staticmethod
    def to_notification(row: NotificationRow) -> Notification:
        """Public: the outbox sender converts rows it claimed (recipient must be loaded)."""
        return PostgresLeaveRepository._to_notification(row)

    @staticmethod
    def _to_notification(row: NotificationRow) -> Notification:
        return Notification(
            id=row.public_id,
            recipient_id=row.recipient.public_id,
            event=NotificationEvent(row.event),
            message=row.message,
            read=row.read_at is not None,
            created_at=row.created_at,
        )

    def _notification_query(self) -> Any:
        return (
            select(NotificationRow)
            .options(joinedload(NotificationRow.recipient, innerjoin=True))
            .where(NotificationRow.tenant_id == self._tenant_id)
        )

    async def add_notification(self, notification: Notification) -> None:
        row = NotificationRow(
            tenant_id=self._tenant_id,
            public_id=notification.id,
            recipient_id=await self._employee_pk(notification.recipient_id),
            event=notification.event.value,
            message=notification.message,
            read_at=notification.created_at if notification.read else None,
            created_at=notification.created_at,
        )
        self._session.add(row)
        await self._session.flush()
        # Transactional outbox (SPEC BR-12): queued in the SAME transaction as the leave
        # action, so it exists if and only if the action is committed.
        self._session.add(NotificationOutboxRow(tenant_id=self._tenant_id, notification_id=row.id))
        await self._session.flush()
        self._notification_rows[notification.id] = row

    async def _notification_row(self, notification_id: str) -> NotificationRow:
        row = await self._session.scalar(
            self._notification_query().where(NotificationRow.public_id == notification_id)
        )
        if row is None:
            raise NotFoundError("Notification", notification_id)
        self._notification_rows[notification_id] = row
        return row

    async def get_notification(self, notification_id: str) -> Notification:
        return self._to_notification(await self._notification_row(notification_id))

    async def save_notification(self, notification: Notification) -> None:
        row = self._notification_rows.get(notification.id) or await self._notification_row(
            notification.id
        )
        if notification.read and row.read_at is None:
            row.read_at = datetime.now(UTC)
        elif not notification.read:
            row.read_at = None
        await self._flush("Notification", notification.id)

    async def list_notifications(self, recipient_id: str) -> list[Notification]:
        rows = await self._session.scalars(
            self._notification_query()
            .where(NotificationRow.recipient_id == await self._employee_pk(recipient_id))
            .order_by(NotificationRow.created_at.desc(), NotificationRow.id.desc())
        )
        notifications = []
        for row in rows.unique():
            self._notification_rows[row.public_id] = row
            notifications.append(self._to_notification(row))
        return notifications

    # ------------------------------------------------------ idempotency keys

    async def claim_idempotency_key(self, employee_id: str, key: str) -> StoredResponse | None:
        """Lock the key for this transaction (advisory lock), then look it up.

        pg_advisory_xact_lock is a lock on a number, not on a row, so it works even
        before the row exists. Two requests with the same key: the second waits here
        until the first commits (or rolls back), then finds its stored response
        (SPEC DB-21). The lock is released automatically at the end of the transaction.
        """
        employee_pk = await self._employee_pk(employee_id)
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": f"idempotency:{self._tenant_id}:{employee_pk}:{key}"},
        )
        row = await self._session.scalar(
            select(IdempotencyKeyRow).where(
                IdempotencyKeyRow.tenant_id == self._tenant_id,
                IdempotencyKeyRow.employee_id == employee_pk,
                IdempotencyKeyRow.key == key,
            )
        )
        if row is None:
            return None
        return StoredResponse(row.request_hash, row.response_status, row.response_body)

    async def save_idempotency_key(
        self, employee_id: str, key: str, response: StoredResponse, request_id: str
    ) -> None:
        request_row = self._request_rows.get(request_id) or await self._request_row(request_id)
        self._session.add(
            IdempotencyKeyRow(
                tenant_id=self._tenant_id,
                employee_id=await self._employee_pk(employee_id),
                key=key,
                request_hash=response.request_hash,
                leave_request_id=request_row.id,
                response_status=response.status,
                response_body=response.body,
            )
        )
        await self._session.flush()


def _entry_type(entitlement_delta: Decimal, used_delta: Decimal, pending_delta: Decimal) -> str:
    """Name a balance movement by its shape (SCHEMA.md 4.8 table)."""
    if used_delta > 0:
        return "confirm"  # approve: pending -> used
    if pending_delta > 0:
        return "reserve"  # apply
    if pending_delta < 0:
        return "release"  # reject or cancel
    return "grant"  # entitlement change (register employee)
