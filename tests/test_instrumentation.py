"""BR-8 / FR-11: the @audit decorator and the timed() context manager."""

import logging
import time
from types import SimpleNamespace

import pytest

from leavedesk.domain.exceptions import InvalidTransitionError
from leavedesk.domain.instrumentation import audit, timed


@audit
def approve(request_id: str) -> SimpleNamespace:
    return SimpleNamespace(id=request_id)


@audit
def reject(request_id: str) -> None:
    raise InvalidTransitionError("approved", "reject")


@audit
async def apply(employee_id: str) -> SimpleNamespace:
    return SimpleNamespace(id="LR-NEW")


def test_success_is_logged(caplog: pytest.LogCaptureFixture) -> None:  # AC-11.1
    caplog.set_level(logging.INFO, logger="leavedesk.audit")
    approve("LR-1")
    assert "action=approve request_id=LR-1 outcome=success" in caplog.text


def test_failure_is_logged_and_still_raised(caplog: pytest.LogCaptureFixture) -> None:  # AC-11.2
    caplog.set_level(logging.INFO, logger="leavedesk.audit")
    with pytest.raises(InvalidTransitionError):
        reject("LR-2")
    assert "action=reject request_id=LR-2 outcome=failed error=InvalidTransitionError" in caplog.text


async def test_async_functions_are_audited(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="leavedesk.audit")
    await apply("E-ANA")
    assert "action=apply request_id=LR-NEW outcome=success" in caplog.text


def test_decorated_function_keeps_its_name() -> None:
    assert approve.__name__ == "approve"


def test_timed_measures_the_block() -> None:
    with timed("short sleep", log=False) as timer:
        time.sleep(0.05)
    assert timer.elapsed_ms >= 45


def test_timed_still_records_when_the_block_fails() -> None:
    with pytest.raises(ValueError), timed("failing block", log=False) as timer:
        raise ValueError("boom")
    assert timer.elapsed_ms > 0
