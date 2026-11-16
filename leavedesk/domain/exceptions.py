"""Custom errors for LeaveDesk.

Every error inherits from LeaveDeskError, so callers can catch one specific
error or every LeaveDesk error at once (SPEC section 8).
"""

from decimal import Decimal


class LeaveDeskError(Exception):
    """Base class for every LeaveDesk domain error."""


class InvalidLeaveRequestError(LeaveDeskError):
    """The request or action breaks a rule (BR-2, BR-3, rejection without a note)."""


class InsufficientBalanceError(LeaveDeskError):
    """The employee does not have enough available days (BR-4)."""

    def __init__(self, leave_type: str, requested: Decimal, available: Decimal) -> None:
        self.leave_type = leave_type
        self.requested = requested
        self.available = available
        super().__init__(
            f"Not enough {leave_type} leave: requested {requested} day(s), "
            f"only {available} available."
        )


class OverlappingLeaveError(LeaveDeskError):
    """The dates overlap an existing pending or approved request (BR-5)."""

    def __init__(self, existing_request_id: str) -> None:
        self.existing_request_id = existing_request_id
        super().__init__(f"Dates overlap existing request {existing_request_id}.")


class InvalidTransitionError(LeaveDeskError):
    """The status change is not allowed by the lifecycle (BR-6)."""

    def __init__(self, current_status: str, action: str) -> None:
        self.current_status = current_status
        self.action = action
        super().__init__(f"Cannot {action} a request that is {current_status}.")


class NotAuthorisedError(LeaveDeskError):
    """The person is not allowed to take this action (BR-6)."""


class ConcurrentUpdateError(LeaveDeskError):
    """The row changed since it was read, so this change was not saved (BR-10, Capstone 3)."""

    def __init__(self, entity: str, entity_id: str) -> None:
        self.entity = entity
        self.entity_id = entity_id
        super().__init__(
            f"{entity} '{entity_id}' was changed by someone else. Reload it and try again."
        )


class IdempotencyKeyReusedError(LeaveDeskError):
    """An Idempotency-Key was sent again with a different request body (BR-11, Capstone 3)."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(
            "This Idempotency-Key was already used with a different request. "
            "Use a new key for a new request."
        )


class DatabaseBusyError(LeaveDeskError):
    """A statement or lock timeout stopped the action; nothing was saved (BR-10, Capstone 3)."""


class NotFoundError(LeaveDeskError):
    """An employee or leave request id does not exist."""

    def __init__(self, entity: str, entity_id: str) -> None:
        self.entity = entity
        self.entity_id = entity_id
        super().__init__(f"{entity} '{entity_id}' not found.")
