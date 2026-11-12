"""LeaveDesk Capstone 1 demo.

Run with:  python -m leavedesk.demo

Plays the happy path and every edge case from SPEC.md against the domain
package and prints a ✓ or ✗ for each check. "Today" is fixed to Mon 9 Nov 2026
(SPEC section 6), so the output is the same on any day. The program exits with
status 1 if any check fails, so it also works as a quick automated check.
"""

import asyncio
import logging
import sys
from collections.abc import Awaitable, Sequence
from datetime import date
from decimal import Decimal

from pydantic import ValidationError

from leavedesk.domain.exceptions import (
    InsufficientBalanceError,
    InvalidLeaveRequestError,
    InvalidTransitionError,
    NotAuthorisedError,
    NotFoundError,
    OverlappingLeaveError,
)
from leavedesk.domain.instrumentation import timed
from leavedesk.domain.models import Employee, LeaveStatus, LeaveType, Notification
from leavedesk.domain.notifications import EmailNotifier, InAppNotifier, Notifier
from leavedesk.domain.policies import default_policies
from leavedesk.domain.repository import InMemoryLeaveRepository
from leavedesk.domain.service import LeaveService

TODAY = date(2026, 11, 9)  # a Monday: the "today" used throughout SPEC section 6
SEND_DELAY_SECONDS = 0.2  # simulated network time for each notification send
ANA, MO, LEE = "E-ANA", "E-MO", "E-LEE"
ANNUAL, SICK, CASUAL = LeaveType.ANNUAL, LeaveType.SICK, LeaveType.CASUAL


# ---------------------------------------------------------------- helpers


def d(day: int, month: int = 11) -> date:
    """Shorthand for a 2026 date: d(11) is 11 Nov, d(11, 12) is 11 Dec."""
    return date(2026, month, day)


def build_service(notifiers: Sequence[Notifier] = ()) -> LeaveService:
    """A fresh service with the SPEC section 6 cast, so every case starts clean."""
    service = LeaveService(
        InMemoryLeaveRepository(), default_policies(), notifiers=notifiers, clock=lambda: TODAY
    )
    service.register_employee(Employee(id=MO, name="Mo", email="mo@leavedesk.test", role="manager"))
    service.register_employee(
        Employee(id=LEE, name="Lee", email="lee@leavedesk.test", role="manager")
    )
    service.register_employee(
        Employee(id=ANA, name="Ana", email="ana@leavedesk.test", role="employee", manager_id=MO)
    )
    return service


def available(service: LeaveService, leave_type: LeaveType = ANNUAL) -> Decimal:
    """Ana's available days for one leave type."""
    return service.get_balances(ANA)[leave_type].available


def heading(title: str) -> None:
    print(f"\n=== {title} ===")


class BrokenEmailNotifier(Notifier):
    """An email channel that always fails, used for EC-15."""

    channel = "broken-email"

    async def deliver(self, notification: Notification) -> None:
        raise ConnectionError("mail server down")


class Checklist:
    """Prints a ✓ or ✗ line for each check and keeps the score."""

    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def record(self, label: str, ok: bool, detail: str) -> None:
        if ok:
            self.passed += 1
        else:
            self.failed += 1
        print(f"  {'✓' if ok else '✗'} {label:<46} {detail}")

    def equal(self, label: str, actual: object, expected: object) -> None:
        """Pass if `actual` equals `expected`."""
        ok = actual == expected
        detail = f"-> {actual}" if ok else f"-> {actual} (expected {expected})"
        self.record(label, ok, detail)

    async def raises(
        self, label: str, expected: type[Exception], action: Awaitable[object]
    ) -> None:
        """Pass only if running `action` raises the `expected` error."""
        try:
            await action
        except expected as error:
            self.record(label, True, f"-> {type(error).__name__}")
        except Exception as error:  # a different error is a failed check, not a crash
            self.record(label, False, f"-> {type(error).__name__} (expected {expected.__name__})")
        else:
            self.record(label, False, f"-> no error (expected {expected.__name__})")


# --------------------------------------------------------------- sections


async def happy_path(check: Checklist) -> None:
    heading("1. Happy path: apply, notify, approve (FR-1, FR-6, FR-9, FR-10, FR-11)")
    email = EmailNotifier(SEND_DELAY_SECONDS)
    in_app = InAppNotifier(SEND_DELAY_SECONDS)
    service = build_service([email, in_app])

    audit_log = logging.getLogger("leavedesk.audit")
    audit_log.setLevel(logging.INFO)  # show the BR-8 audit trail for these two actions
    with timed("apply", log=False) as timer:
        trip = await service.apply(ANA, ANNUAL, d(11), d(13), "Family trip to Ooty")
    approved = await service.approve(trip.id, MO)
    audit_log.setLevel(logging.ERROR)  # from here on, keep the output to the checklist

    check.equal("AC-1.1 Ana applies Wed 11 - Fri 13: status", trip.status, LeaveStatus.PENDING)
    check.equal("AC-1.1 working days", trip.days, Decimal("3"))
    recipients = sorted({n.recipient_id for n in email.outbox})
    check.equal("AC-9.1 notified by email and in-app", recipients, [ANA, MO])
    check.record(
        "AC-9.2 4 sends of 200 ms ran concurrently",
        timer.elapsed_ms < 400,
        f"-> apply took {timer.elapsed_ms:.0f} ms",
    )
    check.equal("AC-6.1 Mo approves: status", approved.status, LeaveStatus.APPROVED)
    check.equal("AC-6.1 annual available after approval", available(service), Decimal("15"))

    half = await service.apply(ANA, ANNUAL, d(17), d(17), "Bank visit and errands", half_day=True)
    check.equal("AC-1.3 half day Tue 17: days", half.days, Decimal("0.5"))
    annual = service.get_balances(ANA)[ANNUAL]
    check.equal(
        "AC-10.1 annual used / pending / available",
        f"{annual.used} / {annual.pending} / {annual.available}",
        "3 / 0.5 / 14.5",
    )

    print("\n  -- cancel, re-apply and reject --")
    weekend = await service.apply(ANA, ANNUAL, d(20), d(23), "Long weekend at home")
    cancelled = await service.cancel(weekend.id, ANA)
    check.equal(
        "AC-8.1 Ana cancels Fri 20 - Mon 23: status", cancelled.status, LeaveStatus.CANCELLED
    )
    check.equal("AC-8.1 days returned: annual available", available(service), Decimal("14.5"))
    again = await service.apply(ANA, ANNUAL, d(20), d(23), "Long weekend at home")
    check.equal("AC-4.2 re-apply the cancelled dates: status", again.status, LeaveStatus.PENDING)
    casual = await service.apply(ANA, CASUAL, d(25), d(25), "Moving to a new flat")
    rejected = await service.reject(casual.id, MO, "Team deadline that week")
    check.equal("AC-7.1 Mo rejects with a note: status", rejected.status, LeaveStatus.REJECTED)
    check.equal("AC-7.1 casual available after rejection", available(service, CASUAL), Decimal("6"))

    for person, name in ((MO, "Mo"), (ANA, "Ana")):
        print(f"\n  {name}'s in-app inbox (oldest first):")
        for notification in in_app.inboxes[person]:
            print(f"    [{notification.event}] {notification.message}")


async def required_edge_cases(check: Checklist) -> None:
    heading("2. Required edge cases EC-1 to EC-5 (SPEC 9.1)")

    await check.raises(
        "EC-1 end date before start date",
        ValidationError,
        build_service().apply(ANA, ANNUAL, d(13), d(11), "Family trip to Ooty"),
    )

    long_weekend = await build_service().apply(ANA, ANNUAL, d(13), d(16), "Long weekend away")
    check.equal("EC-2 weekend inside Fri 13 - Mon 16: days", long_weekend.days, Decimal("2"))

    service = build_service()
    await service.apply(ANA, ANNUAL, d(11), d(13), "Family trip to Ooty")
    await check.raises(
        "EC-3 sick on 13th overlaps annual 11-13",
        OverlappingLeaveError,
        service.apply(ANA, SICK, d(13), d(13), "Fever and cold"),
    )

    service = build_service()
    await check.raises(
        "EC-4 20 days requested, 18 available",
        InsufficientBalanceError,
        service.apply(ANA, ANNUAL, d(16), d(11, 12), "Long holiday abroad"),
    )
    check.equal("EC-4 balance unchanged after refusal", available(service), Decimal("18"))

    half = await build_service().apply(
        ANA, ANNUAL, d(17), d(17), "Bank visit and errands", half_day=True
    )
    check.equal("EC-5 half day Tue 17: days", half.days, Decimal("0.5"))
    await check.raises(
        "EC-5 half day across two dates",
        ValidationError,
        build_service().apply(ANA, ANNUAL, d(11), d(12), "Doctor appointment", half_day=True),
    )


async def further_edge_cases(check: Checklist) -> None:
    heading("3. Further edge cases EC-6 to EC-16 (SPEC 9.1)")
    service = build_service()

    await check.raises(
        "EC-6 weekend only, Sat 14 - Sun 15",
        InvalidLeaveRequestError,
        service.apply(ANA, ANNUAL, d(14), d(15), "Weekend getaway trip"),
    )
    await check.raises(
        "EC-7 half day on Sat 14",
        InvalidLeaveRequestError,
        service.apply(ANA, ANNUAL, d(14), d(14), "Saturday errands run", half_day=True),
    )
    await check.raises(
        "EC-8 annual leave starting Fri 6 (past)",
        InvalidLeaveRequestError,
        service.apply(ANA, ANNUAL, d(6), d(6), "Forgot to apply earlier"),
    )
    sick = await service.apply(ANA, SICK, d(2), d(3), "Fever and cold")
    check.equal("EC-9 sick leave 7 days back: status", sick.status, LeaveStatus.PENDING)
    await check.raises(
        "EC-9 sick leave 10 days back",
        InvalidLeaveRequestError,
        service.apply(ANA, SICK, d(30, 10), d(30, 10), "Fever and cold"),
    )
    await check.raises(
        "EC-10 casual leave over 2 days",
        InvalidLeaveRequestError,
        service.apply(ANA, CASUAL, d(18), d(20), "Moving to a new flat"),
    )

    trip = await service.apply(ANA, ANNUAL, d(11), d(13), "Family trip to Ooty")
    await check.raises(
        "EC-11 Lee (not Ana's manager) approves", NotAuthorisedError, service.approve(trip.id, LEE)
    )
    await check.raises(
        "EC-13 Mo rejects without a note", InvalidLeaveRequestError, service.reject(trip.id, MO)
    )
    await service.approve(trip.id, MO)
    await check.raises(
        "EC-12 Mo approves an approved request",
        InvalidTransitionError,
        service.approve(trip.id, MO),
    )
    await check.raises(
        "EC-14 Ana cancels an approved request",
        InvalidTransitionError,
        service.cancel(trip.id, ANA),
    )
    await check.raises(
        "EC-16 approve an unknown request id", NotFoundError, service.approve("LR-NOPE", MO)
    )

    in_app = InAppNotifier()
    broken = build_service([BrokenEmailNotifier(), in_app])
    request = await broken.apply(ANA, ANNUAL, d(11), d(13), "Family trip to Ooty")
    delivered = sum(len(messages) for messages in in_app.inboxes.values())
    check.record(
        "EC-15 email channel down: request still saved",
        request.status is LeaveStatus.PENDING and delivered == 2,
        f"-> {request.status}, {delivered} in-app delivered",
    )


# ------------------------------------------------------------------- main


async def main() -> int:
    logging.basicConfig(
        level=logging.WARNING,
        stream=sys.stdout,  # same stream as print(), so lines stay in order
        format="      log | %(levelname)s %(name)s: %(message)s",
    )
    print("LeaveDesk - Capstone 1 demo")
    print(f"Today is fixed to {TODAY:%a %d %b %Y}. Ana's manager is Mo; Lee manages someone else.")

    check = Checklist()
    await happy_path(check)
    await required_edge_cases(check)
    await further_edge_cases(check)

    total = check.passed + check.failed
    heading(f"Result: {check.passed}/{total} checks passed")
    return 0 if check.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
