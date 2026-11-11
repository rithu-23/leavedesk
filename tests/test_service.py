"""LeaveService workflow: FR-1, FR-4 to FR-8, FR-10 (failure paths included)."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from leavedesk.domain.balance import LeaveBalance
from leavedesk.domain.exceptions import (
    InsufficientBalanceError,
    InvalidLeaveRequestError,
    InvalidTransitionError,
    NotAuthorisedError,
    NotFoundError,
    OverlappingLeaveError,
)
from leavedesk.domain.models import LeaveRequest, LeaveStatus, LeaveType
from leavedesk.domain.service import LeaveService
from tests.helpers import ANA, LEE, MO, d

ANNUAL = LeaveType.ANNUAL


async def apply_trip(service: LeaveService) -> LeaveRequest:
    """AC-1.1's request: annual leave Wed 11 - Fri 13 Nov (3 working days)."""
    return await service.apply(ANA, ANNUAL, d(11), d(13), "Family trip to Ooty")


def annual(service: LeaveService) -> LeaveBalance:
    return service.get_balances(ANA)[ANNUAL]


# ---------------------------------------------------------------- FR-1, FR-2


async def test_apply_saves_a_pending_request_and_reserves_days(service: LeaveService) -> None:
    request = await apply_trip(service)  # AC-1.1
    assert request.status is LeaveStatus.PENDING
    assert request.days == Decimal("3")
    assert (annual(service).pending, annual(service).available) == (Decimal("3"), Decimal("15"))


async def test_bad_input_is_refused_before_anything_is_saved(service: LeaveService) -> None:
    with pytest.raises(ValidationError):  # FR-2 through the service
        await service.apply(ANA, ANNUAL, d(13), d(11), "Family trip to Ooty")
    assert annual(service).available == Decimal("18")


# ---------------------------------------------------------------- FR-4, FR-5


async def test_overlapping_request_is_refused(service: LeaveService) -> None:  # AC-4.1
    await apply_trip(service)
    with pytest.raises(OverlappingLeaveError):
        await service.apply(ANA, LeaveType.SICK, d(13), d(13), "Fever and cold")
    assert service.get_balances(ANA)[LeaveType.SICK].available == Decimal("12")


async def test_cancelled_dates_can_be_requested_again(service: LeaveService) -> None:  # AC-4.2
    trip = await apply_trip(service)
    await service.cancel(trip.id, ANA)
    again = await apply_trip(service)
    assert again.status is LeaveStatus.PENDING


async def test_insufficient_balance_is_refused_and_nothing_changes(service: LeaveService) -> None:
    with pytest.raises(InsufficientBalanceError):  # AC-5.1
        await service.apply(ANA, ANNUAL, d(16), d(11, 12), "Long holiday abroad")
    assert annual(service).available == Decimal("18")


# ---------------------------------------------------------------- FR-6


async def test_approve_moves_days_to_used(service: LeaveService) -> None:  # AC-6.1
    trip = await apply_trip(service)
    approved = await service.approve(trip.id, MO)
    assert approved.status is LeaveStatus.APPROVED
    assert approved.decided_by == MO
    balance = annual(service)
    assert (balance.used, balance.pending, balance.available) == (
        Decimal("3"),
        Decimal("0"),
        Decimal("15"),
    )


async def test_only_the_requesters_manager_can_approve(service: LeaveService) -> None:  # AC-6.2
    trip = await apply_trip(service)
    with pytest.raises(NotAuthorisedError):
        await service.approve(trip.id, LEE)
    approved = await service.approve(trip.id, MO)  # still pending, so Mo can approve
    assert approved.status is LeaveStatus.APPROVED


async def test_manager_cannot_approve_their_own_request(service: LeaveService) -> None:
    own = await service.apply(MO, ANNUAL, d(11), d(13), "Family trip to Ooty")
    with pytest.raises(NotAuthorisedError):
        await service.approve(own.id, MO)


async def test_approving_twice_is_an_invalid_transition(service: LeaveService) -> None:  # AC-6.3
    trip = await apply_trip(service)
    await service.approve(trip.id, MO)
    with pytest.raises(InvalidTransitionError):
        await service.approve(trip.id, MO)


# ---------------------------------------------------------------- FR-7


async def test_reject_with_note_releases_days(service: LeaveService) -> None:  # AC-7.1
    trip = await apply_trip(service)
    rejected = await service.reject(trip.id, MO, "Team deadline that week")
    assert rejected.status is LeaveStatus.REJECTED
    assert rejected.decision_note == "Team deadline that week"
    assert annual(service).available == Decimal("18")


@pytest.mark.parametrize("note", [None, "", "   "])
async def test_reject_without_a_note_is_refused(service: LeaveService, note: str | None) -> None:
    trip = await apply_trip(service)  # AC-7.2
    with pytest.raises(InvalidLeaveRequestError):
        await service.reject(trip.id, MO, note)
    assert annual(service).pending == Decimal("3")


async def test_rejecting_an_approved_request_is_invalid(service: LeaveService) -> None:  # AC-7.3
    trip = await apply_trip(service)
    await service.approve(trip.id, MO)
    with pytest.raises(InvalidTransitionError):
        await service.reject(trip.id, MO, "Too late now")


# ---------------------------------------------------------------- FR-8


async def test_cancel_releases_days(service: LeaveService) -> None:  # AC-8.1
    trip = await apply_trip(service)
    cancelled = await service.cancel(trip.id, ANA)
    assert cancelled.status is LeaveStatus.CANCELLED
    assert annual(service).available == Decimal("18")


async def test_only_the_owner_can_cancel(service: LeaveService) -> None:  # AC-8.2
    trip = await apply_trip(service)
    with pytest.raises(NotAuthorisedError):
        await service.cancel(trip.id, MO)


async def test_cancelling_an_approved_request_is_invalid(service: LeaveService) -> None:  # AC-8.3
    trip = await apply_trip(service)
    await service.approve(trip.id, MO)
    with pytest.raises(InvalidTransitionError):
        await service.cancel(trip.id, ANA)


# ---------------------------------------------------------------- FR-10, EC-16


async def test_balances_after_approval_and_half_day(service: LeaveService) -> None:  # AC-10.1
    trip = await apply_trip(service)
    await service.approve(trip.id, MO)
    await service.apply(ANA, ANNUAL, d(17), d(17), "Bank visit and errands", half_day=True)
    balances = service.get_balances(ANA)
    assert (balances[ANNUAL].used, balances[ANNUAL].pending, balances[ANNUAL].available) == (
        Decimal("3"),
        Decimal("0.5"),
        Decimal("14.5"),
    )
    assert balances[LeaveType.SICK].available == Decimal("12")
    assert balances[LeaveType.CASUAL].available == Decimal("6")


async def test_unknown_request_id_is_not_found(service: LeaveService) -> None:  # EC-16
    with pytest.raises(NotFoundError):
        await service.approve("LR-NOPE", MO)
