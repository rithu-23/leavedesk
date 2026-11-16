"""Login accounts and the three demo users.

UserDirectory is what the API needs from any account store. UserStore keeps
accounts in memory; leavedesk/db/users.py stores them in PostgreSQL.
"""

from dataclasses import dataclass
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


class UserDirectory(Protocol):
    """Login accounts, looked up by email (case-insensitive)."""

    def add(self, account: UserAccount) -> None: ...

    def find_by_email(self, email: str) -> UserAccount | None: ...


class UserStore:
    """In-memory UserDirectory (Capstones 1 and 2, and the fast test runs)."""

    def __init__(self) -> None:
        self._by_email: dict[str, UserAccount] = {}

    def add(self, account: UserAccount) -> None:
        self._by_email[account.email.lower()] = account

    def find_by_email(self, email: str) -> UserAccount | None:
        return self._by_email.get(email.strip().lower())


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
