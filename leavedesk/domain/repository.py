"""Storage for LeaveDesk behind a repository interface.

LeaveService depends only on the abstract LeaveRepository. Capstones 1 and 2
use the in-memory implementation; Capstone 3 adds a PostgreSQL implementation
of the same interface without changing the leave rules.
"""

from abc import ABC, abstractmethod
from copy import deepcopy

from leavedesk.domain.balance import LeaveBalance
from leavedesk.domain.exceptions import NotFoundError
from leavedesk.domain.models import Employee, LeaveRequest, LeaveStatus, LeaveType, Notification


class LeaveRepository(ABC):
    """The contract every storage implementation must follow."""

    # ----- Employees -----
    @abstractmethod
    def add_employee(self, employee: Employee) -> None: ...

    @abstractmethod
    def get_employee(self, employee_id: str) -> Employee:
        """Return the employee, or raise NotFoundError."""

    @abstractmethod
    def list_employees(self) -> list[Employee]:
        """Return every employee."""

    # ----- Leave requests -----
    @abstractmethod
    def add_request(self, request: LeaveRequest) -> None:
        """Store a new request; its id must not exist yet."""

    @abstractmethod
    def save_request(self, request: LeaveRequest) -> None:
        """Store changes to an existing request, or raise NotFoundError."""

    @abstractmethod
    def get_request(self, request_id: str) -> LeaveRequest:
        """Return the request, or raise NotFoundError."""

    @abstractmethod
    def list_requests(
        self, employee_id: str | None = None, status: LeaveStatus | None = None
    ) -> list[LeaveRequest]:
        """Return requests, optionally filtered, ordered by start date."""

    # ----- Balances -----
    @abstractmethod
    def save_balance(self, balance: LeaveBalance) -> None:
        """Create or update a balance."""

    @abstractmethod
    def get_balance(self, employee_id: str, leave_type: LeaveType) -> LeaveBalance:
        """Return the balance, or raise NotFoundError."""

    # ----- Notifications -----
    @abstractmethod
    def add_notification(self, notification: Notification) -> None: ...

    @abstractmethod
    def get_notification(self, notification_id: str) -> Notification:
        """Return the notification, or raise NotFoundError."""

    @abstractmethod
    def save_notification(self, notification: Notification) -> None:
        """Store changes to an existing notification, or raise NotFoundError."""

    @abstractmethod
    def list_notifications(self, recipient_id: str) -> list[Notification]:
        """Return the recipient's notifications, newest first."""


class InMemoryLeaveRepository(LeaveRepository):
    """Keeps everything in dictionaries while the program runs.

    Objects are stored and returned as deep copies, so a change only counts
    once it is saved, just like a real database.
    """

    def __init__(self) -> None:
        self._employees: dict[str, Employee] = {}
        self._requests: dict[str, LeaveRequest] = {}
        self._balances: dict[tuple[str, LeaveType], LeaveBalance] = {}
        self._notifications: dict[str, Notification] = {}

    # ----- Employees -----
    def add_employee(self, employee: Employee) -> None:
        if employee.id in self._employees:
            raise ValueError(f"employee {employee.id} already exists")
        self._employees[employee.id] = deepcopy(employee)

    def get_employee(self, employee_id: str) -> Employee:
        if employee_id not in self._employees:
            raise NotFoundError("Employee", employee_id)
        return deepcopy(self._employees[employee_id])

    def list_employees(self) -> list[Employee]:
        return [deepcopy(employee) for employee in self._employees.values()]

    # ----- Leave requests -----
    def add_request(self, request: LeaveRequest) -> None:
        if request.id in self._requests:
            raise ValueError(f"leave request {request.id} already exists")
        self._requests[request.id] = deepcopy(request)

    def save_request(self, request: LeaveRequest) -> None:
        if request.id not in self._requests:
            raise NotFoundError("LeaveRequest", request.id)
        self._requests[request.id] = deepcopy(request)

    def get_request(self, request_id: str) -> LeaveRequest:
        if request_id not in self._requests:
            raise NotFoundError("LeaveRequest", request_id)
        return deepcopy(self._requests[request_id])

    def list_requests(
        self, employee_id: str | None = None, status: LeaveStatus | None = None
    ) -> list[LeaveRequest]:
        matches = [
            request
            for request in self._requests.values()
            if (employee_id is None or request.employee_id == employee_id)
            and (status is None or request.status is status)
        ]
        return [deepcopy(request) for request in sorted(matches, key=lambda r: r.start_date)]

    # ----- Balances -----
    def save_balance(self, balance: LeaveBalance) -> None:
        self._balances[(balance.employee_id, balance.leave_type)] = deepcopy(balance)

    def get_balance(self, employee_id: str, leave_type: LeaveType) -> LeaveBalance:
        key = (employee_id, leave_type)
        if key not in self._balances:
            raise NotFoundError("LeaveBalance", f"{employee_id}/{leave_type}")
        return deepcopy(self._balances[key])

    # ----- Notifications -----
    def add_notification(self, notification: Notification) -> None:
        if notification.id in self._notifications:
            raise ValueError(f"notification {notification.id} already exists")
        self._notifications[notification.id] = deepcopy(notification)

    def get_notification(self, notification_id: str) -> Notification:
        if notification_id not in self._notifications:
            raise NotFoundError("Notification", notification_id)
        return deepcopy(self._notifications[notification_id])

    def save_notification(self, notification: Notification) -> None:
        if notification.id not in self._notifications:
            raise NotFoundError("Notification", notification.id)
        self._notifications[notification.id] = deepcopy(notification)

    def list_notifications(self, recipient_id: str) -> list[Notification]:
        mine = [n for n in self._notifications.values() if n.recipient_id == recipient_id]
        return [deepcopy(n) for n in sorted(mine, key=lambda n: n.created_at, reverse=True)]
