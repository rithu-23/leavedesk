"""FR-9 notifications: recipients (BR-7), concurrency and failure isolation."""

import time
from collections.abc import Awaitable, Callable
from decimal import Decimal

import pytest

from leavedesk.domain.models import LeaveRequest, LeaveStatus, LeaveType, Notification, NotificationEvent
from leavedesk.domain.notifications import (
    DeliveryReport,
    EmailNotifier,
    InAppNotifier,
    Notifier,
    send_all,
)
from leavedesk.domain.service import LeaveService
from tests.helpers import ANA, MO, build_service, d

Action = Callable[[LeaveService, str], Awaitable[LeaveRequest]]


class BrokenEmailNotifier(Notifier):
    """A channel that always fails."""

    channel = "broken-email"

    async def deliver(self, notification: Notification) -> None:
        raise ConnectionError("mail server down")


async def apply_trip(service: LeaveService) -> LeaveRequest:
    return await service.apply(ANA, LeaveType.ANNUAL, d(11), d(13), "Family trip to Ooty")


async def test_submit_notifies_employee_and_manager_on_every_channel(
    email: EmailNotifier, in_app: InAppNotifier
) -> None:  # AC-9.1
    service = build_service([email, in_app])
    await apply_trip(service)
    assert sorted(n.recipient_id for n in email.outbox) == [ANA, MO]
    assert set(in_app.inboxes) == {ANA, MO}


@pytest.mark.parametrize(
    ("event", "act", "expected"),
    [
        pytest.param(
            NotificationEvent.APPROVED,
            lambda s, request_id: s.approve(request_id, MO),
            [ANA],
            id="AC-9.3 approved goes to the employee",
        ),
        pytest.param(
            NotificationEvent.REJECTED,
            lambda s, request_id: s.reject(request_id, MO, "Team deadline that week"),
            [ANA],
            id="AC-9.3 rejected goes to the employee",
        ),
        pytest.param(
            NotificationEvent.CANCELLED,
            lambda s, request_id: s.cancel(request_id, ANA),
            [MO],
            id="AC-9.3 cancelled goes to the manager",
        ),
    ],
)
async def test_each_event_reaches_its_br7_recipients(
    email: EmailNotifier, event: NotificationEvent, act: Action, expected: list[str]
) -> None:
    service = build_service([email])
    trip = await apply_trip(service)
    await act(service, trip.id)
    assert sorted({n.recipient_id for n in email.outbox if n.event == event}) == expected


async def test_notifications_arrive_unread(email: EmailNotifier) -> None:  # AC-9.3
    service = build_service([email])
    await apply_trip(service)
    assert email.outbox
    assert all(not n.read for n in email.outbox)


async def test_sends_run_concurrently() -> None:  # AC-9.2
    service = build_service([EmailNotifier(delay_seconds=0.2), InAppNotifier(delay_seconds=0.2)])
    start = time.perf_counter()
    await apply_trip(service)
    elapsed = time.perf_counter() - start
    assert elapsed < 0.4  # 4 sends of 0.2 s: about 0.2 s together, 0.8 s one at a time


async def test_failing_channel_does_not_undo_the_action(
    in_app: InAppNotifier, caplog: pytest.LogCaptureFixture
) -> None:  # AC-9.4
    service = build_service([BrokenEmailNotifier(), in_app])
    request = await apply_trip(service)
    assert request.status is LeaveStatus.PENDING
    assert service.get_balances(ANA)[LeaveType.ANNUAL].pending == Decimal("3")
    assert sum(len(messages) for messages in in_app.inboxes.values()) == 2
    assert "send failed channel=broken-email" in caplog.text


async def test_send_all_counts_failures(in_app: InAppNotifier) -> None:
    notes = [Notification(recipient_id=ANA, event=NotificationEvent.SUBMITTED, message="Hello")]
    report = await send_all(notes, [BrokenEmailNotifier(), in_app])
    assert report == DeliveryReport(sent=1, failed=1)
