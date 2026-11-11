"""Leave balances and their accounting rules (BR-1, BR-4).

LeaveBalance is a dataclass, not a Pydantic model: it is created and changed
only by our own code (LeaveService), never from user input, so it needs no
input validation, just correct behaviour.
"""

from dataclasses import dataclass
from decimal import Decimal

from leavedesk.domain.exceptions import InsufficientBalanceError
from leavedesk.domain.models import LeaveType

# Days each employee starts the year with (BR-1).
DEFAULT_ENTITLEMENTS: dict[LeaveType, Decimal] = {
    LeaveType.ANNUAL: Decimal("18"),
    LeaveType.SICK: Decimal("12"),
    LeaveType.CASUAL: Decimal("6"),
}


@dataclass
class LeaveBalance:
    """One employee's balance for one leave type (SPEC 3.5).

    Change it only through reserve(), confirm() and release(), so the BR-4
    rules are enforced in one place (encapsulation).
    """

    employee_id: str
    leave_type: LeaveType
    entitlement: Decimal
    used: Decimal = Decimal("0")
    pending: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        """Runs right after the generated __init__; guards against impossible starting values."""
        if self.entitlement < 0 or self.used < 0 or self.pending < 0:
            raise ValueError("balance values cannot be negative")

    @property
    def available(self) -> Decimal:
        """Days that can still be requested: entitlement - used - pending."""
        return self.entitlement - self.used - self.pending

    def reserve(self, days: Decimal) -> None:
        """Apply: hold days for a new pending request (BR-4)."""
        self._check_positive(days)
        if days > self.available:
            raise InsufficientBalanceError(self.leave_type, days, self.available)
        self.pending += days

    def confirm(self, days: Decimal) -> None:
        """Approve: move held days from pending to used (BR-4)."""
        self._check_positive(days)
        self._check_pending(days)
        self.pending -= days
        self.used += days

    def release(self, days: Decimal) -> None:
        """Reject or cancel: give held days back (BR-4)."""
        self._check_positive(days)
        self._check_pending(days)
        self.pending -= days

    @staticmethod
    def _check_positive(days: Decimal) -> None:
        if days <= 0:
            raise ValueError("days must be greater than 0")

    def _check_pending(self, days: Decimal) -> None:
        if days > self.pending:
            raise ValueError(f"cannot move {days} day(s); only {self.pending} pending")


def default_balances(employee_id: str) -> dict[LeaveType, LeaveBalance]:
    """A fresh set of balances for a new employee, one per leave type (BR-1)."""
    return {
        leave_type: LeaveBalance(employee_id, leave_type, entitlement)
        for leave_type, entitlement in DEFAULT_ENTITLEMENTS.items()
    }
