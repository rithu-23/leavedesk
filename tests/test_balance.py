"""BR-1 starting balances and BR-4 balance accounting."""

from decimal import Decimal

import pytest

from leavedesk.domain.balance import LeaveBalance, default_balances
from leavedesk.domain.exceptions import InsufficientBalanceError
from leavedesk.domain.models import LeaveType


def annual_balance() -> LeaveBalance:
    return LeaveBalance("E-ANA", LeaveType.ANNUAL, Decimal("18"))


def test_default_entitlements_match_br1() -> None:
    balances = default_balances("E-ANA")
    assert {leave_type: b.entitlement for leave_type, b in balances.items()} == {
        LeaveType.ANNUAL: Decimal("18"),
        LeaveType.SICK: Decimal("12"),
        LeaveType.CASUAL: Decimal("6"),
    }


def test_reserve_holds_days_as_pending() -> None:  # AC-1.1
    balance = annual_balance()
    balance.reserve(Decimal("3"))
    assert (balance.pending, balance.available) == (Decimal("3"), Decimal("15"))


def test_confirm_moves_pending_days_to_used() -> None:  # AC-6.1
    balance = annual_balance()
    balance.reserve(Decimal("3"))
    balance.confirm(Decimal("3"))
    assert (balance.used, balance.pending, balance.available) == (
        Decimal("3"),
        Decimal("0"),
        Decimal("15"),
    )


def test_release_gives_pending_days_back() -> None:  # AC-7.1, AC-8.1
    balance = annual_balance()
    balance.reserve(Decimal("3"))
    balance.release(Decimal("3"))
    assert balance.available == Decimal("18")


def test_reserving_too_many_days_changes_nothing() -> None:  # AC-5.1
    balance = annual_balance()
    with pytest.raises(InsufficientBalanceError) as caught:
        balance.reserve(Decimal("20"))
    assert caught.value.available == Decimal("18")
    assert balance.pending == Decimal("0")


def test_pending_days_count_against_the_balance() -> None:  # AC-5.2
    balance = annual_balance()
    balance.reserve(Decimal("15"))
    with pytest.raises(InsufficientBalanceError):
        balance.reserve(Decimal("4"))


@pytest.mark.parametrize("days", [Decimal("0"), Decimal("-1")])
def test_zero_or_negative_days_are_refused(days: Decimal) -> None:
    with pytest.raises(ValueError):
        annual_balance().reserve(days)


def test_cannot_confirm_more_days_than_pending() -> None:
    balance = annual_balance()
    balance.reserve(Decimal("3"))
    with pytest.raises(ValueError):
        balance.confirm(Decimal("4"))


def test_negative_starting_values_are_refused() -> None:
    with pytest.raises(ValueError):
        LeaveBalance("E-ANA", LeaveType.ANNUAL, Decimal("-1"))
