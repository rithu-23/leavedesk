"""API-1 to API-5, API-27, API-28: login, tokens, request IDs and password storage."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from leavedesk.api.settings import Settings
from tests.api.support import PASSWORD, error_code, login


def test_login_returns_a_bearer_token(client: TestClient) -> None:  # API-1
    response = login(client, "ana@leavedesk.test")
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["expires_in"] == 30 * 60


def test_wrong_password_gives_a_generic_401(client: TestClient) -> None:  # API-2
    response = login(client, "ana@leavedesk.test", "wrong-password")
    assert response.status_code == 401
    assert error_code(response) == "UNAUTHENTICATED"
    assert response.json()["error"]["message"] == "Invalid email or password"


def test_unknown_email_gives_exactly_the_same_401(client: TestClient) -> None:  # API-3
    wrong_password = login(client, "ana@leavedesk.test", "wrong-password")
    unknown_email = login(client, "nobody@leavedesk.test")
    assert unknown_email.status_code == wrong_password.status_code == 401
    assert unknown_email.json()["error"]["message"] == wrong_password.json()["error"]["message"]


def test_missing_token_is_401_with_matching_request_id(client: TestClient) -> None:  # API-4
    response = client.get("/leave-requests")
    assert response.status_code == 401
    assert error_code(response) == "UNAUTHENTICATED"
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]


def make_token(secret: str, minutes_from_now: int) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": "E-ANA",
        "role": "employee",
        "iat": now,
        "exp": now + timedelta(minutes=minutes_from_now),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.mark.parametrize("case", ["expired", "signed with another secret"])
def test_expired_or_forged_token_is_401(
    client: TestClient, settings: Settings, case: str
) -> None:  # API-5
    if case == "expired":
        token = make_token(settings.jwt_secret.get_secret_value(), minutes_from_now=-5)
    else:
        token = make_token("an-attacker-secret-that-is-also-long-enough", minutes_from_now=30)
    response = client.get("/leave-requests", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert error_code(response) == "UNAUTHENTICATED"


def test_every_response_has_a_request_id(client: TestClient) -> None:  # API-27
    assert client.get("/health").headers["x-request-id"]


def test_incoming_request_id_is_reused(client: TestClient) -> None:  # API-27
    response = client.get("/health", headers={"X-Request-ID": "trace-123"})
    assert response.headers["x-request-id"] == "trace-123"


def test_unsafe_incoming_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "bad id!"})
    assert response.headers["x-request-id"] != "bad id!"


def test_passwords_are_stored_as_argon2id_hashes(client: TestClient) -> None:  # API-28
    users = client.app.state.leavedesk.users  # type: ignore[attr-defined]
    for email in ("ana@leavedesk.test", "mo@leavedesk.test", "lee@leavedesk.test"):
        account = users.find_by_email(email)
        assert account is not None
        assert account.password_hash.startswith("$argon2id$")
        assert PASSWORD not in account.password_hash
