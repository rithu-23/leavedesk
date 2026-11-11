"""Leave policies: the rules that differ by leave type (BR-3).

LeavePolicy is an abstract base class. validate() runs the checks shared by
every leave type, then calls check_type_rules(), which each subclass must
implement with its own rule (the "template method" pattern).
"""

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal
from typing import ClassVar

from leavedesk.domain.exceptions import InvalidLeaveRequestError
from leavedesk.domain.models import LeaveRequest, LeaveType


class LeavePolicy(ABC):
    """Base class for all leave policies. Cannot be used directly."""

    leave_type: ClassVar[LeaveType]

    def validate(self, request: LeaveRequest, days: Decimal, today: date) -> None:
        """Run the shared checks, then this leave type's own rule."""
        if request.leave_type is not self.leave_type:
            raise ValueError(f"{type(self).__name__} cannot validate {request.leave_type} leave")
        if days <= 0:
            raise InvalidLeaveRequestError("The request contains no working days (BR-2).")
        self.check_type_rules(request, days, today)

    @abstractmethod
    def check_type_rules(self, request: LeaveRequest, days: Decimal, today: date) -> None:
        """Each subclass enforces its own BR-3 rule here."""


def _reject_past_start(request: LeaveRequest, today: date) -> None:
    """Shared rule for leave that must be planned ahead (Annual, Casual)."""
    if request.start_date < today:
        raise InvalidLeaveRequestError(
            f"{request.leave_type} leave cannot start in the past (BR-3)."
        )


class AnnualLeavePolicy(LeavePolicy):
    """Annual leave cannot start before today (BR-3)."""

    leave_type = LeaveType.ANNUAL

    def check_type_rules(self, request: LeaveRequest, days: Decimal, today: date) -> None:
        _reject_past_start(request, today)


class SickLeavePolicy(LeavePolicy):
    """Sick leave may start up to 7 calendar days before today (BR-3)."""

    leave_type = LeaveType.SICK
    MAX_BACKDATE_DAYS: ClassVar[int] = 7

    def check_type_rules(self, request: LeaveRequest, days: Decimal, today: date) -> None:
        days_back = (today - request.start_date).days
        if days_back > self.MAX_BACKDATE_DAYS:
            raise InvalidLeaveRequestError(
                f"Sick leave can be backdated by at most {self.MAX_BACKDATE_DAYS} days (BR-3); "
                f"this one starts {days_back} days ago."
            )


class CasualLeavePolicy(LeavePolicy):
    """Casual leave cannot start before today and is at most 2 working days (BR-3)."""

    leave_type = LeaveType.CASUAL
    MAX_DAYS_PER_REQUEST: ClassVar[Decimal] = Decimal("2")

    def check_type_rules(self, request: LeaveRequest, days: Decimal, today: date) -> None:
        _reject_past_start(request, today)
        if days > self.MAX_DAYS_PER_REQUEST:
            raise InvalidLeaveRequestError(
                f"Casual leave is limited to {self.MAX_DAYS_PER_REQUEST} working days "
                f"per request (BR-3); this one uses {days}."
            )


def default_policies() -> dict[LeaveType, LeavePolicy]:
    """One policy per leave type, ready to hand to LeaveService."""
    policies: list[LeavePolicy] = [AnnualLeavePolicy(), SickLeavePolicy(), CasualLeavePolicy()]
    return {policy.leave_type: policy for policy in policies}
