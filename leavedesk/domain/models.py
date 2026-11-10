"""Domain models for LeaveDesk, validated with Pydantic v2.

These models check that data is well-formed on its own (SPEC section 9.2).
Rules that need other data, such as balance, overlap, policies and who may act,
belong to LeaveService, not here.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Simple email shape: something@something.something, no spaces (SPEC 9.2).
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


def _new_id(prefix: str) -> str:
    """Create a short unique id such as 'LR-3f9a1c2b'."""
    return f"{prefix}-{uuid4().hex[:8]}"


def _utc_now() -> datetime:
    """Current time in UTC, so timestamps never depend on the computer's time zone."""
    return datetime.now(UTC)


# ---------- Enums: fixed lists of allowed values ----------


class Role(StrEnum):
    EMPLOYEE = "employee"
    MANAGER = "manager"


class LeaveType(StrEnum):
    ANNUAL = "ANNUAL"
    SICK = "SICK"
    CASUAL = "CASUAL"


class LeaveStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class NotificationEvent(StrEnum):
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


# ---------- Models ----------


class Employee(BaseModel):
    """A person who can apply for leave; managers are employees with role MANAGER (SPEC 3.1, 3.2)."""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(pattern=EMAIL_PATTERN)
    role: Role
    manager_id: str | None = None

    @property
    def is_manager(self) -> bool:
        return self.role is Role.MANAGER


class LeaveRequest(BaseModel):
    """A request for leave over a date range (SPEC 3.4)."""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    id: str = Field(default_factory=lambda: _new_id("LR"))
    employee_id: str = Field(min_length=1)
    leave_type: LeaveType
    start_date: date
    end_date: date
    half_day: bool = False
    reason: str = Field(min_length=10, max_length=500)
    status: LeaveStatus = LeaveStatus.PENDING
    days: Decimal = Field(default=Decimal("0"), ge=0, multiple_of=Decimal("0.5"))
    created_at: datetime = Field(default_factory=_utc_now)
    decided_by: str | None = None
    decision_note: str | None = None

    @model_validator(mode="after")
    def check_dates(self) -> Self:
        """Rules that compare two fields, so they can't be simple Field limits."""
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        if self.half_day and self.start_date != self.end_date:
            raise ValueError("a half day must start and end on the same date")
        return self


class Notification(BaseModel):
    """A message telling someone that a leave event happened (SPEC 3.6)."""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    id: str = Field(default_factory=lambda: _new_id("N"))
    recipient_id: str = Field(min_length=1)
    event: NotificationEvent
    message: str = Field(min_length=1)
    read: bool = False
    created_at: datetime = Field(default_factory=_utc_now)
