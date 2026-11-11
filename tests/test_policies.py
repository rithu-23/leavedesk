"""BR-3 leave-type policies, and the abstract base class."""

from datetime import date
from decimal import Decimal

import pytest

from leavedesk.domain.dates import count_working_days
from leavedesk.domain.exceptions import InvalidLeaveRequestError
from leavedesk.domain.models import LeaveRequest, LeaveType
from leavedesk.domain.policies import AnnualLeavePolicy, LeavePolicy, default_policies
from tests.helpers import TODAY, d


def check_policy(leave_type: LeaveType, start: date, end: date) -> None:
    request = LeaveRequest(
        employee_id="E-ANA",
        leave_type=leave_type,
        start_date=start,
        end_date=end,
        reason="Testing the leave policy",
    )
    days = count_working_days(start, end)
    default_policies()[leave_type].validate(request, days, TODAY)


@pytest.mark.parametrize(
    ("leave_type", "start", "end"),
    [
        pytest.param(LeaveType.ANNUAL, d(11), d(13), id="annual from today onwards"),
        pytest.param(LeaveType.SICK, d(2), d(3), id="AC-3.2 sick exactly 7 days back"),
        pytest.param(LeaveType.CASUAL, d(18), d(19), id="casual for 2 days"),
    ],
)
def test_policy_accepts(leave_type: LeaveType, start: date, end: date) -> None:
    check_policy(leave_type, start, end)  # passes if no error is raised


@pytest.mark.parametrize(
    ("leave_type", "start", "end"),
    [
        pytest.param(LeaveType.ANNUAL, d(6), d(6), id="AC-3.1 annual in the past"),
        pytest.param(LeaveType.SICK, d(30, 10), d(30, 10), id="AC-3.3 sick 10 days back"),
        pytest.param(LeaveType.CASUAL, d(18), d(20), id="AC-3.4 casual over 2 days"),
        pytest.param(LeaveType.ANNUAL, d(14), d(15), id="AC-1.4 no working days"),
    ],
)
def test_policy_refuses(leave_type: LeaveType, start: date, end: date) -> None:
    with pytest.raises(InvalidLeaveRequestError):
        check_policy(leave_type, start, end)


def test_abstract_policy_cannot_be_created() -> None:
    with pytest.raises(TypeError):
        LeavePolicy()  # type: ignore[abstract]


def test_policy_refuses_a_request_of_another_leave_type() -> None:
    sick_request = LeaveRequest(
        employee_id="E-ANA",
        leave_type=LeaveType.SICK,
        start_date=d(11),
        end_date=d(11),
        reason="Testing the wrong policy",
    )
    with pytest.raises(ValueError):
        AnnualLeavePolicy().validate(sick_request, Decimal("1"), TODAY)
