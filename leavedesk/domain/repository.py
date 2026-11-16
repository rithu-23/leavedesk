"""Storage for LeaveDesk behind a repository interface.

LeaveService depends only on the abstract LeaveRepository. Capstones 1 and 2
use the in-memory implementation; Capstone 3 adds a PostgreSQL implementation
of the same interface without changing the leave rules.

Every method is async (Capstone 3, SPEC T15): storage is I/O, so a database
implementation must be able to wait for PostgreSQL without blocking the
event loop. The in-memory implementation has nothing to wait for, but keeps
the same signatures so the two are interchangeable.

`lock=True` on get_request() and get_balance() asks the storage to lock that
row until the current transaction ends (SELECT ... FOR UPDATE), so two
concurrent actions cannot both change it (SPEC BR-10). The in-memory
implementation ignores it.
"""

from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from leavedesk.domain.balance import LeaveBalance
from leavedesk.domain.exceptions import NotFoundError
from leavedesk.domain.models import Employee, LeaveRequest, LeaveStatus, LeaveType, Notification
from leavedesk.domain.pagination import RequestPage, decode_cursor, encode_cursor


@dataclass(frozen=True)
class StoredResponse:
    """The first answer to a submit made with an Idempotency-Key (SPEC BR-11)."""

    request_hash: str
    status: int
    body: dict[str, Any]


class LeaveRepository(ABC):
    """The contract every storage implementation must follow."""

    # ----- Employees -----
    @abstractmethod
    async def add_employee(self, employee: Employee) -> None: ...

    @abstractmethod
    async def get_employee(self, employee_id: str) -> Employee:
        """Return the employee, or raise NotFoundError."""

    @abstractmethod
    async def list_employees(self) -> list[Employee]:
        """Return every employee."""

    # ----- Leave requests -----
    @abstractmethod
    async def add_request(self, request: LeaveRequest) -> None:
        """Store a new request; its id must not exist yet."""

    @abstractmethod
    async def save_request(self, request: LeaveRequest) -> None:
        """Store changes to an existing request, or raise NotFoundError.

        Sets request.version to the new version (one higher), so the caller can
        return it. Raises ConcurrentUpdateError if the stored row changed since it
        was read (PostgreSQL implementation).
        """

    @abstractmethod
    async def get_request(self, request_id: str, *, lock: bool = False) -> LeaveRequest:
        """Return the request, or raise NotFoundError. lock=True: lock the row (BR-10)."""

    @abstractmethod
    async def list_requests(
        self, employee_id: str | None = None, status: LeaveStatus | None = None
    ) -> list[LeaveRequest]:
        """Return requests, optionally filtered, ordered by start date."""

    # ----- Balances -----
    @abstractmethod
    async def save_balance(self, balance: LeaveBalance, *, request_id: str | None = None) -> None:
        """Create or update a balance.

        request_id names the leave request that caused the change (None for the initial
        grant). The PostgreSQL repository records it on the ledger row (SCHEMA.md 4.8).
        """

    @abstractmethod
    async def get_balance(
        self, employee_id: str, leave_type: LeaveType, *, lock: bool = False
    ) -> LeaveBalance:
        """Return the balance, or raise NotFoundError. lock=True: lock the row (BR-10)."""

    # ----- Notifications -----
    @abstractmethod
    async def add_notification(self, notification: Notification) -> None: ...

    @abstractmethod
    async def get_notification(self, notification_id: str) -> Notification:
        """Return the notification, or raise NotFoundError."""

    @abstractmethod
    async def save_notification(self, notification: Notification) -> None:
        """Store changes to an existing notification, or raise NotFoundError."""

    @abstractmethod
    async def list_notifications(self, recipient_id: str) -> list[Notification]:
        """Return the recipient's notifications, newest first."""

    @abstractmethod
    async def page_requests(
        self,
        *,
        employee_ids: set[str],
        status: LeaveStatus | None = None,
        descending: bool = False,
        limit: int = 20,
        offset: int = 0,
        cursor: str | None = None,
    ) -> RequestPage:
        """One page of requests by start date (then a tie-breaker), filtered in storage.

        cursor: continue strictly after the position it names (keyset pagination);
        offset is then ignored. Raises ValueError for an invalid cursor.
        """

    # ----- Idempotency keys (Capstone 3) -----
    @abstractmethod
    async def claim_idempotency_key(self, employee_id: str, key: str) -> StoredResponse | None:
        """Return the stored first response for this employee's key, or None if it is new.

        The PostgreSQL implementation also holds a lock on the key until the transaction
        ends, so a second request with the same key waits, then sees the first result.
        """

    @abstractmethod
    async def save_idempotency_key(
        self, employee_id: str, key: str, response: StoredResponse, request_id: str
    ) -> None:
        """Store the first response, in the same transaction as the new request."""


class InMemoryLeaveRepository(LeaveRepository):
    """Keeps everything in dictionaries while the program runs.

    Objects are stored and returned as deep copies, so a change only counts
    once it is saved, just like a real database. It has no transactions, so
    `lock` is accepted and ignored: a single event loop never runs two
    of these methods at the same time.
    """

    def __init__(self) -> None:
        self._employees: dict[str, Employee] = {}
        self._requests: dict[str, LeaveRequest] = {}
        self._balances: dict[tuple[str, LeaveType], LeaveBalance] = {}
        self._notifications: dict[str, Notification] = {}
        self._idempotency: dict[tuple[str, str], StoredResponse] = {}

    # ----- Employees -----
    async def add_employee(self, employee: Employee) -> None:
        if employee.id in self._employees:
            raise ValueError(f"employee {employee.id} already exists")
        self._employees[employee.id] = deepcopy(employee)

    async def get_employee(self, employee_id: str) -> Employee:
        if employee_id not in self._employees:
            raise NotFoundError("Employee", employee_id)
        return deepcopy(self._employees[employee_id])

    async def list_employees(self) -> list[Employee]:
        return [deepcopy(employee) for employee in self._employees.values()]

    # ----- Leave requests -----
    async def add_request(self, request: LeaveRequest) -> None:
        if request.id in self._requests:
            raise ValueError(f"leave request {request.id} already exists")
        self._requests[request.id] = deepcopy(request)

    async def save_request(self, request: LeaveRequest) -> None:
        if request.id not in self._requests:
            raise NotFoundError("LeaveRequest", request.id)
        request.version = self._requests[request.id].version + 1  # the caller sees the new version
        self._requests[request.id] = deepcopy(request)

    async def get_request(self, request_id: str, *, lock: bool = False) -> LeaveRequest:
        if request_id not in self._requests:
            raise NotFoundError("LeaveRequest", request_id)
        return deepcopy(self._requests[request_id])

    async def list_requests(
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
    async def save_balance(self, balance: LeaveBalance, *, request_id: str | None = None) -> None:
        self._balances[(balance.employee_id, balance.leave_type)] = deepcopy(balance)

    async def get_balance(
        self, employee_id: str, leave_type: LeaveType, *, lock: bool = False
    ) -> LeaveBalance:
        key = (employee_id, leave_type)
        if key not in self._balances:
            raise NotFoundError("LeaveBalance", f"{employee_id}/{leave_type}")
        return deepcopy(self._balances[key])

    # ----- Notifications -----
    async def add_notification(self, notification: Notification) -> None:
        if notification.id in self._notifications:
            raise ValueError(f"notification {notification.id} already exists")
        self._notifications[notification.id] = deepcopy(notification)

    async def get_notification(self, notification_id: str) -> Notification:
        if notification_id not in self._notifications:
            raise NotFoundError("Notification", notification_id)
        return deepcopy(self._notifications[notification_id])

    async def save_notification(self, notification: Notification) -> None:
        if notification.id not in self._notifications:
            raise NotFoundError("Notification", notification.id)
        self._notifications[notification.id] = deepcopy(notification)

    async def list_notifications(self, recipient_id: str) -> list[Notification]:
        mine = [n for n in self._notifications.values() if n.recipient_id == recipient_id]
        return [deepcopy(n) for n in sorted(mine, key=lambda n: n.created_at, reverse=True)]

    async def page_requests(
        self,
        *,
        employee_ids: set[str],
        status: LeaveStatus | None = None,
        descending: bool = False,
        limit: int = 20,
        offset: int = 0,
        cursor: str | None = None,
    ) -> RequestPage:
        # (start_date, insertion position) is unique, so the order is total.
        keyed = [
            ((request.start_date, position), request)
            for position, request in enumerate(self._requests.values())
            if request.employee_id in employee_ids and (status is None or request.status is status)
        ]
        keyed.sort(key=lambda pair: pair[0], reverse=descending)
        if cursor is not None:
            after = decode_cursor(cursor)
            keyed = [p for p in keyed if (p[0] < after if descending else p[0] > after)]
            window = keyed[:limit]
            more = len(keyed) > limit
        else:
            window = keyed[offset : offset + limit]
            more = len(keyed) > offset + limit
        total = sum(
            1
            for r in self._requests.values()
            if r.employee_id in employee_ids and (status is None or r.status is status)
        )
        last = window[-1][0] if window else None
        return RequestPage(
            items=[deepcopy(request) for _, request in window],
            total=total,
            next_cursor=encode_cursor(*last) if more and last else None,
        )

    # ----- Idempotency keys -----
    async def claim_idempotency_key(self, employee_id: str, key: str) -> StoredResponse | None:
        return self._idempotency.get((employee_id, key))

    async def save_idempotency_key(
        self, employee_id: str, key: str, response: StoredResponse, request_id: str
    ) -> None:
        self._idempotency[(employee_id, key)] = response
