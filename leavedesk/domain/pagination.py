"""Keyset pagination helpers (API_SPEC 3.1, SPEC DB-32 to DB-34).

A cursor names a position in the list's order: the start date and a tie-breaker
number of the last row on the previous page. Each storage chooses the number
(PostgreSQL: the row's internal id; in memory: insertion order). Clients see an
opaque base64url string and must send it back unchanged.
"""

import base64
import binascii
from dataclasses import dataclass
from datetime import date

from leavedesk.domain.models import LeaveRequest


@dataclass(frozen=True)
class RequestPage:
    items: list[LeaveRequest]
    total: int  # all matching rows, ignoring limit/offset/cursor
    next_cursor: str | None  # None on the last page


def encode_cursor(start_date: date, key: int) -> str:
    raw = f"{start_date.isoformat()}|{key}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[date, int]:
    """Raise ValueError for anything that is not a cursor this API produced."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        start, key = base64.urlsafe_b64decode(padded.encode()).decode().split("|")
        return date.fromisoformat(start), int(key)
    except (ValueError, binascii.Error, UnicodeDecodeError) as error:
        raise ValueError("invalid cursor") from error
