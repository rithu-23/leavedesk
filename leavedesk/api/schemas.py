"""Request and response shapes (API_SPEC.md section 4)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Generic, Self, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from leavedesk.domain.balance import LeaveBalance
from leavedesk.domain.models import (
    LeaveRequest,
    LeaveStatus,
    LeaveType,
    Notification,
    NotificationEvent,
)

T = TypeVar("T")


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class LeaveRequestCreate(BaseModel):
    """employee_id is deliberately absent: it always comes from the token."""

    leave_type: LeaveType
    start_date: date
    end_date: date
    reason: str
    half_day: bool = False


class RejectBody(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    reason: str = Field(min_length=1, max_length=500)


class LeaveRequestOut(BaseModel):
    id: str
    employee_id: str
    leave_type: LeaveType
    start_date: date
    end_date: date
    half_day: bool
    reason: str
    status: LeaveStatus
    days: Decimal
    created_at: datetime
    decided_by: str | None
    decision_note: str | None

    @classmethod
    def from_domain(cls, request: LeaveRequest) -> Self:
        return cls.model_validate(request.model_dump())


class BalanceOut(BaseModel):
    leave_type: LeaveType
    entitlement: Decimal
    used: Decimal
    pending: Decimal
    available: Decimal

    @classmethod
    def from_domain(cls, balance: LeaveBalance) -> Self:
        return cls(
            leave_type=balance.leave_type,
            entitlement=balance.entitlement,
            used=balance.used,
            pending=balance.pending,
            available=balance.available,
        )


class NotificationOut(BaseModel):
    id: str
    event: NotificationEvent
    message: str
    read: bool
    created_at: datetime

    @classmethod
    def from_domain(cls, notification: Notification) -> Self:
        return cls.model_validate(notification.model_dump())


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int
