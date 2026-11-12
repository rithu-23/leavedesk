"""Shared helpers for the API tests."""

from typing import Any

from fastapi.testclient import TestClient
from httpx import Response

from leavedesk.domain.models import Notification
from leavedesk.domain.notifications import Notifier

PASSWORD = "test-password-123"
JWT_SECRET = "test-secret-that-is-at-least-32-characters-long"

# AC-1.1's request: annual leave Wed 11 - Fri 13 Nov 2026 (3 working days).
TRIP: dict[str, Any] = {
    "leave_type": "ANNUAL",
    "start_date": "2026-11-11",
    "end_date": "2026-11-13",
    "reason": "Family trip to Ooty",
}


class RecordingNotifier(Notifier):
    """Mock notifier: records what would have been sent instead of sending it."""

    channel = "recording"

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[Notification] = []

    async def deliver(self, notification: Notification) -> None:
        self.sent.append(notification)


def login(client: TestClient, email: str, password: str = PASSWORD) -> Response:
    return client.post("/auth/login", data={"username": email, "password": password})


def auth_headers(client: TestClient, email: str) -> dict[str, str]:
    response = login(client, email)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def apply(client: TestClient, headers: dict[str, str], **changes: Any) -> Response:
    """POST /leave-requests with TRIP, overriding any fields given."""
    return client.post("/leave-requests", json={**TRIP, **changes}, headers=headers)


def error_code(response: Response) -> str:
    return str(response.json()["error"]["code"])
