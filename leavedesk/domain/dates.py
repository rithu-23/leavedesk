"""Date calculations for LeaveDesk: working days (BR-2) and overlap detection (BR-5).

Every function here is pure: it uses only its inputs and returns a result,
which makes it simple to test.
"""

from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal

from leavedesk.domain.models import LeaveRequest, LeaveStatus

HALF_DAY = Decimal("0.5")

# Requests in these statuses still hold dates; rejected and cancelled ones do not (BR-5).
ACTIVE_STATUSES = frozenset({LeaveStatus.PENDING, LeaveStatus.APPROVED})


def is_working_day(day: date) -> bool:
    """Monday to Friday are working days; Saturday and Sunday are not (BR-2)."""
    return day.weekday() < 5


def count_working_days(start: date, end: date, half_day: bool = False) -> Decimal:
    """Count the working days from start to end, both included (BR-2).

    A half day counts as 0.5 if it falls on a working day, otherwise 0.
    Returns 0 when the range holds no working days; the service turns that
    into an InvalidLeaveRequestError.
    """
    if end < start:
        raise ValueError("end must not be before start")

    if half_day:
        if start != end:
            raise ValueError("a half day must start and end on the same date")
        return HALF_DAY if is_working_day(start) else Decimal("0")

    total_days = (end - start).days + 1
    working = sum(
        1 for offset in range(total_days) if is_working_day(start + timedelta(days=offset))
    )
    return Decimal(working)


def ranges_overlap(a_start: date, a_end: date, b_start: date, b_end: date) -> bool:
    """Two inclusive date ranges overlap if each starts on or before the other ends (BR-5)."""
    return a_start <= b_end and b_start <= a_end


def find_overlap(new: LeaveRequest, existing: Iterable[LeaveRequest]) -> LeaveRequest | None:
    """Return the first active request of the same employee that overlaps `new`, or None (BR-5)."""
    for other in existing:
        if (
            other.id != new.id
            and other.employee_id == new.employee_id
            and other.status in ACTIVE_STATUSES
            and ranges_overlap(new.start_date, new.end_date, other.start_date, other.end_date)
        ):
            return other
    return None
