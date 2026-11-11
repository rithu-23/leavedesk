"""FR-2: badly formed input is refused by the Pydantic models (SPEC 9.2)."""

from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from leavedesk.domain.models import Employee, LeaveRequest, LeaveStatus

VALID: dict[str, Any] = {
    "employee_id": "E-ANA",
    "leave_type": "ANNUAL",
    "start_date": "2026-11-11",
    "end_date": "2026-11-13",
    "reason": "Family trip to Ooty",
}


def test_valid_request_starts_pending_and_parses_dates() -> None:
    request = LeaveRequest(**VALID)
    assert request.status is LeaveStatus.PENDING
    assert request.start_date == date(2026, 11, 11)


def test_each_request_gets_its_own_id() -> None:
    assert LeaveRequest(**VALID).id != LeaveRequest(**VALID).id


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"start_date": "2026-11-13", "end_date": "2026-11-11"}, id="AC-2.1 end before start"),
        pytest.param({"reason": "   trip   "}, id="AC-2.2 reason too short after trimming"),
        pytest.param({"end_date": "2026-11-12", "half_day": True}, id="AC-2.3 half day over two dates"),
        pytest.param({"status": "on_hold"}, id="AC-2.4 unknown status"),
    ],
)
def test_invalid_request_input_is_rejected(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        LeaveRequest(**{**VALID, **changes})


def test_status_change_after_creation_is_validated() -> None:
    request = LeaveRequest(**VALID)
    with pytest.raises(ValidationError):
        request.status = "on_hold"  # type: ignore[assignment]


def test_employee_email_must_look_like_an_email() -> None:
    with pytest.raises(ValidationError):
        Employee(id="E-X", name="X", email="not-an-email", role="employee")


def test_employee_name_is_trimmed() -> None:
    employee = Employee(id="E-ANA", name="  Ana  ", email="ana@leavedesk.test", role="employee")
    assert employee.name == "Ana"
