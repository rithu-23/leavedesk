"""LeaveService: the leave workflow (FR-1, FR-4 to FR-8, FR-10).

LeaveService is composed of a repository, one policy per leave type and a
clock (dependency injection). It depends only on the LeaveRepository
interface, so storage can change in Capstone 3 without changing these rules.

Every check runs before anything is saved, so a failed action leaves no
partial changes behind.
"""

from collections.abc import Callable, Mapping
from datetime import date

from leavedesk.domain.balance import LeaveBalance, default_balances
from leavedesk.domain.dates import count_working_days, find_overlap
from leavedesk.domain.exceptions import (
    InvalidLeaveRequestError,
    InvalidTransitionError,
    NotAuthorisedError,
    OverlappingLeaveError,
)
from leavedesk.domain.instrumentation import audit
from leavedesk.domain.models import (
    Employee,
    LeaveRequest,
    LeaveStatus,
    LeaveType,
    Notification,
    NotificationEvent,
)
from leavedesk.domain.policies import LeavePolicy
from leavedesk.domain.repository import LeaveRepository


class LeaveService:
    """Applies, approves, rejects and cancels leave while keeping balances correct."""

    def __init__(
        self,
        repository: LeaveRepository,
        policies: Mapping[LeaveType, LeavePolicy],
        clock: Callable[[], date] = date.today,
    ) -> None:
        self._repo = repository
        self._policies = policies
        self._clock = clock

    # ------------------------------------------------------------------ setup

    @audit
    def register_employee(self, employee: Employee) -> Employee:
        """Add an employee and give them their starting balances (BR-1)."""
        self._repo.add_employee(employee)
        for balance in default_balances(employee.id).values():
            self._repo.save_balance(balance)
        return employee

    # --------------------------------------------------------------- actions

    @audit
    async def apply(
        self,
        employee_id: str,
        leave_type: LeaveType,
        start_date: date,
        end_date: date,
        reason: str,
        half_day: bool = False,
    ) -> LeaveRequest:
        """Submit a leave request (FR-1 to FR-5)."""
        employee = self._repo.get_employee(employee_id)
        request = LeaveRequest(  # Pydantic checks the input here (FR-2)
            employee_id=employee.id,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            reason=reason,
            half_day=half_day,
        )

        days = count_working_days(request.start_date, request.end_date, request.half_day)
        self._policies[request.leave_type].validate(request, days, self._clock())  # FR-3

        clash = find_overlap(request, self._repo.list_requests(employee_id=employee.id))
        if clash is not None:  # FR-4
            raise OverlappingLeaveError(clash.id)

        balance = self._repo.get_balance(employee.id, request.leave_type)
        balance.reserve(days)  # FR-5: raises InsufficientBalanceError if too few days

        # All checks passed: now save.
        request.days = days
        self._repo.add_request(request)
        self._repo.save_balance(balance)

        notices = [
            Notification(
                recipient_id=employee.id,
                event=NotificationEvent.SUBMITTED,
                message=f"Your request for {self._describe(request)} was submitted.",
            )
        ]
        if employee.manager_id:
            notices.append(
                Notification(
                    recipient_id=employee.manager_id,
                    event=NotificationEvent.SUBMITTED,
                    message=f"{employee.name} requested {days} day(s) of {self._describe(request)}.",
                )
            )
        self._emit(notices)
        return request

    @audit
    async def approve(self, request_id: str, approver_id: str) -> LeaveRequest:
        """Approve a pending request (FR-6)."""
        request, employee = self._load(request_id)
        self._ensure_manager_of(approver_id, employee)
        self._ensure_pending(request, "approve")

        balance = self._repo.get_balance(employee.id, request.leave_type)
        balance.confirm(request.days)
        request.status = LeaveStatus.APPROVED
        request.decided_by = approver_id

        self._repo.save_request(request)
        self._repo.save_balance(balance)
        self._emit([
            Notification(
                recipient_id=employee.id,
                event=NotificationEvent.APPROVED,
                message=f"Your request for {self._describe(request)} was approved.",
            )
        ])
        return request

    @audit
    async def reject(self, request_id: str, approver_id: str, note: str | None = None) -> LeaveRequest:
        """Reject a pending request; a reason is required (FR-7)."""
        request, employee = self._load(request_id)
        self._ensure_manager_of(approver_id, employee)
        self._ensure_pending(request, "reject")
        if note is None or not note.strip():
            raise InvalidLeaveRequestError("A rejection needs a reason (BR-6).")

        balance = self._repo.get_balance(employee.id, request.leave_type)
        balance.release(request.days)
        request.status = LeaveStatus.REJECTED
        request.decided_by = approver_id
        request.decision_note = note.strip()

        self._repo.save_request(request)
        self._repo.save_balance(balance)
        self._emit([
            Notification(
                recipient_id=employee.id,
                event=NotificationEvent.REJECTED,
                message=f"Your request for {self._describe(request)} was rejected: {request.decision_note}",
            )
        ])
        return request

    @audit
    async def cancel(self, request_id: str, employee_id: str) -> LeaveRequest:
        """Cancel your own pending request (FR-8)."""
        request, employee = self._load(request_id)
        if request.employee_id != employee_id:
            raise NotAuthorisedError("Only the employee who made the request can cancel it (BR-6).")
        self._ensure_pending(request, "cancel")

        balance = self._repo.get_balance(employee.id, request.leave_type)
        balance.release(request.days)
        request.status = LeaveStatus.CANCELLED

        self._repo.save_request(request)
        self._repo.save_balance(balance)
        if employee.manager_id:
            self._emit([
                Notification(
                    recipient_id=employee.manager_id,
                    event=NotificationEvent.CANCELLED,
                    message=f"{employee.name} cancelled their request for {self._describe(request)}.",
                )
            ])
        return request

    # ---------------------------------------------------------------- queries

    @audit
    def get_balances(self, employee_id: str) -> dict[LeaveType, LeaveBalance]:
        """All of an employee's balances, one per leave type (FR-10)."""
        self._repo.get_employee(employee_id)  # raises NotFoundError for unknown ids
        return {leave_type: self._repo.get_balance(employee_id, leave_type) for leave_type in LeaveType}

    def list_notifications(self, recipient_id: str) -> list[Notification]:
        """A person's notifications, newest first."""
        return self._repo.list_notifications(recipient_id)

    # ---------------------------------------------------------------- helpers

    def _load(self, request_id: str) -> tuple[LeaveRequest, Employee]:
        """Fetch a request and the employee who made it (NotFoundError if missing)."""
        request = self._repo.get_request(request_id)
        return request, self._repo.get_employee(request.employee_id)

    def _ensure_manager_of(self, approver_id: str, employee: Employee) -> None:
        """Only the requester's own manager may decide (BR-6); this also blocks self-approval."""
        approver = self._repo.get_employee(approver_id)
        if not approver.is_manager or employee.manager_id != approver.id:
            raise NotAuthorisedError(f"{approver.id} is not the manager of {employee.id} (BR-6).")

    @staticmethod
    def _ensure_pending(request: LeaveRequest, action: str) -> None:
        """Only pending requests can change status (BR-6)."""
        if request.status is not LeaveStatus.PENDING:
            raise InvalidTransitionError(request.status, action)

    def _emit(self, notifications: list[Notification]) -> None:
        """Store notifications (BR-7). Sending them is added in the notifications task (T11)."""
        for notification in notifications:
            self._repo.add_notification(notification)

    @staticmethod
    def _describe(request: LeaveRequest) -> str:
        """Readable summary such as 'annual leave (11 Nov – 13 Nov)'."""
        start, end = request.start_date, request.end_date
        dates = f"{start:%d %b}" if start == end else f"{start:%d %b} – {end:%d %b}"
        return f"{request.leave_type.value.lower()} leave ({dates})"
