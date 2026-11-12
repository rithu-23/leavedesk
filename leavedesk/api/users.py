"""Login accounts and the three demo users (in memory until Capstone 3)."""

from dataclasses import dataclass

from leavedesk.api.security import hash_password
from leavedesk.domain.models import Employee, Role
from leavedesk.domain.service import LeaveService


@dataclass(frozen=True)
class UserAccount:
    employee_id: str
    email: str
    password_hash: str


class UserStore:
    """Login accounts, looked up by email (case-insensitive)."""

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


def seed_demo_data(service: LeaveService, users: UserStore, password: str) -> None:
    """Register the demo employees and give each a login with a hashed password."""
    for employee in DEMO_EMPLOYEES:
        service.register_employee(employee)
        users.add(UserAccount(employee.id, employee.email, hash_password(password)))
