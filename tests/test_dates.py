"""BR-2 working-day counting and BR-5 overlap detection."""

from datetime import date
from decimal import Decimal

import pytest

from leavedesk.domain.dates import count_working_days, find_overlap, ranges_overlap
from leavedesk.domain.models import LeaveRequest, LeaveStatus
from tests.helpers import ANA, MO, d


@pytest.mark.parametrize(
    ("start", "end", "half_day", "expected"),
    [
        pytest.param(d(11), d(13), False, Decimal("3"), id="AC-1.1 Wed to Fri"),
        pytest.param(d(13), d(16), False, Decimal("2"), id="AC-1.2 weekend not counted"),
        pytest.param(d(17), d(17), True, Decimal("0.5"), id="AC-1.3 half day"),
        pytest.param(d(14), d(15), False, Decimal("0"), id="AC-1.4 weekend only"),
        pytest.param(d(14), d(14), True, Decimal("0"), id="EC-7 half day on a Saturday"),
        pytest.param(d(16), d(11, 12), False, Decimal("20"), id="AC-5.1 four full weeks"),
    ],
)
def test_count_working_days(start: date, end: date, half_day: bool, expected: Decimal) -> None:
    assert count_working_days(start, end, half_day) == expected


def test_end_before_start_is_refused() -> None:
    with pytest.raises(ValueError):
        count_working_days(d(13), d(11))


@pytest.mark.parametrize(
    ("a_start", "a_end", "b_start", "b_end", "expected"),
    [
        pytest.param(d(11), d(13), d(11), d(13), True, id="same range"),
        pytest.param(d(11), d(13), d(12), d(16), True, id="partial overlap"),
        pytest.param(d(11), d(13), d(12), d(12), True, id="one inside the other"),
        pytest.param(d(11), d(13), d(13), d(16), True, id="touching on one day"),
        pytest.param(d(11), d(12), d(13), d(16), False, id="next to each other, no shared day"),
    ],
)
def test_ranges_overlap(
    a_start: date, a_end: date, b_start: date, b_end: date, expected: bool
) -> None:
    assert ranges_overlap(a_start, a_end, b_start, b_end) is expected


def make_request(
    start: date, end: date, employee_id: str = ANA, status: LeaveStatus = LeaveStatus.PENDING
) -> LeaveRequest:
    return LeaveRequest(
        employee_id=employee_id,
        leave_type="ANNUAL",
        start_date=start,
        end_date=end,
        reason="Testing overlap detection",
        status=status,
    )


def test_find_overlap_returns_the_clashing_request() -> None:  # AC-4.1
    existing = make_request(d(11), d(13))
    assert find_overlap(make_request(d(13), d(13)), [existing]) is existing


@pytest.mark.parametrize("status", [LeaveStatus.CANCELLED, LeaveStatus.REJECTED])
def test_find_overlap_ignores_inactive_requests(status: LeaveStatus) -> None:  # AC-4.2
    existing = make_request(d(11), d(13), status=status)
    assert find_overlap(make_request(d(13), d(13)), [existing]) is None


def test_find_overlap_ignores_other_employees() -> None:
    existing = make_request(d(11), d(13))
    assert find_overlap(make_request(d(13), d(13), employee_id=MO), [existing]) is None
