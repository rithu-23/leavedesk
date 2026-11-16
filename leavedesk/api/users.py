"""Login accounts and the three demo users.

UserDirectory is what the API needs from any account store. UserStore keeps
accounts in memory; leavedesk/db/users.py stores them in PostgreSQL.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Protocol

from leavedesk.api.security import hash_password
from leavedesk.domain.exceptions import NotFoundError
from leavedesk.domain.models import Employee, Role
from leavedesk.domain.repository import LeaveRepository
from leavedesk.domain.service import LeaveService


@dataclass(frozen=True)
class UserAccount:
    employee_id: str
    email: str
    password_hash: str
    failed_login_count: int = 0
    locked_until: datetime | None = None  # SPEC BR-13

    def is_locked(self, now: datetime) -> bool:
        return self.locked_until is not None and self.locked_until > now


class UserDirectory(Protocol):
    """Login accounts, looked up by email (case-insensitive)."""

    def add(self, account: UserAccount) -> None: ...

    def find_by_email(self, email: str) -> UserAccount | None: ...

    def record_failed_login(
        self, employee_id: str, *, max_attempts: int, lock_minutes: int, now: datetime
    ) -> bool:
        """Count one wrong password; lock the account at max_attempts. True if it just locked."""
        ...

    def record_successful_login(self, employee_id: str, *, now: datetime) -> None:
        """Reset the failure count and any expired lock."""
        ...


def next_failure_state(
    account: UserAccount, *, max_attempts: int, lock_minutes: int, now: datetime
) -> tuple[int, datetime | None]:
    """The count and lock after one more wrong password (shared by both stores' tests).

    A lock that has already expired starts the count again from zero, so one typo
    after a lockout does not lock the account again straight away.
    """
    expired = account.locked_until is not None and account.locked_until <= now
    count = 1 if expired else account.failed_login_count + 1
    locked_until = now + timedelta(minutes=lock_minutes) if count >= max_attempts else None
    return count, locked_until


class UserStore:
    """In-memory UserDirectory (Capstones 1 and 2, and the fast test runs)."""

    def __init__(self) -> None:
        self._by_email: dict[str, UserAccount] = {}

    def add(self, account: UserAccount) -> None:
        self._by_email[account.email.lower()] = account

    def find_by_email(self, email: str) -> UserAccount | None:
        return self._by_email.get(email.strip().lower())

    def _by_employee(self, employee_id: str) -> UserAccount:
        return next(a for a in self._by_email.values() if a.employee_id == employee_id)

    def record_failed_login(
        self, employee_id: str, *, max_attempts: int, lock_minutes: int, now: datetime
    ) -> bool:
        account = self._by_employee(employee_id)
        count, locked_until = next_failure_state(
            account, max_attempts=max_attempts, lock_minutes=lock_minutes, now=now
        )
        self.add(replace(account, failed_login_count=count, locked_until=locked_until))
        return locked_until is not None and count == max_attempts

    def record_successful_login(self, employee_id: str, *, now: datetime) -> None:
        account = self._by_employee(employee_id)
        self.add(replace(account, failed_login_count=0, locked_until=None))


DEMO_EMPLOYEES = (
    Employee(id="E-MO", name="Mo", email="mo@leavedesk.test", role=Role.MANAGER),
    Employee(id="E-LEE", name="Lee", email="lee@leavedesk.test", role=Role.MANAGER),
    Employee(
        id="E-ANA", name="Ana", email="ana@leavedesk.test", role=Role.EMPLOYEE, manager_id="E-MO"
    ),
)


async def seed_demo_employees(repository: LeaveRepository, service: LeaveService) -> bool:
    """Register the demo employees unless they already exist. Returns True if it added them.

    A database keeps its data between restarts (SPEC DB-2), so seeding must be
    safe to run on every start-up. The check reads the repository directly, so a
    normal first start does not log a failed audited call.
    """
    try:
        await repository.get_employee(DEMO_EMPLOYEES[0].id)
    except NotFoundError:
        for employee in DEMO_EMPLOYEES:
            await service.register_employee(employee)
        return True
    return False


def seed_demo_logins(users: UserDirectory, password: str) -> None:
    """Give each demo employee a login with an Argon2id-hashed password (skips existing ones)."""
    for employee in DEMO_EMPLOYEES:
        if users.find_by_email(employee.email) is None:
            users.add(UserAccount(employee.id, employee.email, hash_password(password)))
