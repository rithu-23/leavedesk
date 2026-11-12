"""Fixtures for the API tests: a fresh app per test, a mocked notifier, signed-in users."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from leavedesk.api.main import create_app
from leavedesk.api.settings import Settings
from tests.api.support import JWT_SECRET, PASSWORD, RecordingNotifier, auth_headers
from tests.helpers import TODAY


@pytest.fixture
def settings() -> Settings:
    """Test settings; _env_file=None means your real .env is never read."""
    return Settings(jwt_secret=JWT_SECRET, demo_password=PASSWORD, _env_file=None)  # type: ignore[arg-type, call-arg]


@pytest.fixture
def notifier() -> RecordingNotifier:
    return RecordingNotifier()


@pytest.fixture
def client(settings: Settings, notifier: RecordingNotifier) -> Iterator[TestClient]:
    app = create_app(settings, clock=lambda: TODAY, notifiers=[notifier])
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def ana(client: TestClient) -> dict[str, str]:
    return auth_headers(client, "ana@leavedesk.test")


@pytest.fixture
def mo(client: TestClient) -> dict[str, str]:
    return auth_headers(client, "mo@leavedesk.test")


@pytest.fixture
def lee(client: TestClient) -> dict[str, str]:
    return auth_headers(client, "lee@leavedesk.test")
