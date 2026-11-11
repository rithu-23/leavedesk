"""Shared test data: the SPEC section 6 cast and a fixed 'today'."""

from collections.abc import Sequence
from datetime import date

from leavedesk.domain.models import Employee
from leavedesk.domain.notifications import Notifier
from leavedesk.domain.policies import default_policies
from leavedesk.domain.repository import InMemoryLeaveRepository
from leavedesk.domain.service import LeaveService

TODAY = date(2026, 11, 9)  # a Monday, as in SPEC section 6
ANA, MO, LEE = "E-ANA", "E-MO", "E-LEE"


def d(day: int, month: int = 11) -> date:
    """Shorthand for a 2026 date: d(11) is 11 Nov, d(11, 12) is 11 Dec."""
    return date(2026, month, day)


def build_service(notifiers: Sequence[Notifier] = ()) -> LeaveService:
    """A fresh LeaveService with Ana (reports to Mo), Mo and Lee registered."""
    service = LeaveService(
        InMemoryLeaveRepository(), default_policies(), notifiers=notifiers, clock=lambda: TODAY
    )
    service.register_employee(
        Employee(id=MO, name="Mo", email="mo@leavedesk.test", role="manager")
    )
    service.register_employee(
        Employee(id=LEE, name="Lee", email="lee@leavedesk.test", role="manager")
    )
    service.register_employee(
        Employee(id=ANA, name="Ana", email="ana@leavedesk.test", role="employee", manager_id=MO)
    )
    return service
