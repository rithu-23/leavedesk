"""BR-10: which rows each action asks the repository to lock, and in what order.

The in-memory repository ignores `lock`, so these tests use a recording
repository to check what LeaveService *asks for*. The PostgreSQL repository
(Capstone 3) turns each lock=True into SELECT ... FOR UPDATE; a consistent
order (request, then balance) is what prevents deadlocks (SPEC BR-10).
"""

from decimal import Decimal

from leavedesk.domain.balance import LeaveBalance
from leavedesk.domain.models import Employee, LeaveRequest, LeaveType
from leavedesk.domain.policies import default_policies
from leavedesk.domain.repository import InMemoryLeaveRepository
from leavedesk.domain.service import LeaveService
from tests.helpers import ANA, LEE, MO, TODAY, d

ANNUAL = LeaveType.ANNUAL


class LockRecordingRepository(InMemoryLeaveRepository):
    """Remembers every get_request / get_balance call made with lock=True."""

    def __init__(self) -> None:
        super().__init__()
        self.locks: list[str] = []

    async def get_request(self, request_id: str, *, lock: bool = False) -> LeaveRequest:
        if lock:
            self.locks.append("request")
        return await super().get_request(request_id, lock=lock)

    async def get_balance(
        self, employee_id: str, leave_type: LeaveType, *, lock: bool = False
    ) -> LeaveBalance:
        if lock:
            self.locks.append("balance")
        return await super().get_balance(employee_id, leave_type, lock=lock)


async def build() -> tuple[LeaveService, LockRecordingRepository]:
    repo = LockRecordingRepository()
    service = LeaveService(repo, default_policies(), clock=lambda: TODAY)
    await service.register_employee(
        Employee(id=MO, name="Mo", email="mo@leavedesk.test", role="manager")
    )
    await service.register_employee(
        Employee(id=LEE, name="Lee", email="lee@leavedesk.test", role="manager")
    )
    await service.register_employee(
        Employee(id=ANA, name="Ana", email="ana@leavedesk.test", role="employee", manager_id=MO)
    )
    return service, repo


async def test_apply_locks_only_the_balance() -> None:
    service, repo = await build()
    await service.apply(ANA, ANNUAL, d(11), d(13), "Family trip to Ooty")
    assert repo.locks == ["balance"]


async def test_approve_reject_and_cancel_lock_request_then_balance() -> None:
    service, repo = await build()
    first = await service.apply(ANA, ANNUAL, d(11), d(11), "Family trip to Ooty")
    second = await service.apply(ANA, ANNUAL, d(12), d(12), "Family trip to Ooty")
    third = await service.apply(ANA, ANNUAL, d(13), d(13), "Family trip to Ooty")
    for action in (
        service.approve(first.id, MO),
        service.reject(second.id, MO, "Team deadline that week"),
        service.cancel(third.id, ANA),
    ):
        repo.locks.clear()
        await action
        assert repo.locks == ["request", "balance"]  # same order every time: no deadlocks


async def test_reading_balances_takes_no_locks() -> None:
    service, repo = await build()
    balances = await service.get_balances(ANA)
    assert balances[ANNUAL].available == Decimal("18")
    assert repo.locks == []
