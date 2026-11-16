"""SPEC BR-13 / FR-17: login lockout after 5 wrong passwords (DB-27, DB-28).

Runs in both storage modes: in memory with `pytest`, on PostgreSQL with
scripts/pytest-postgres.sh (then the counts live in the users table).
"""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.api.support import PASSWORD

ANA = "ana@leavedesk.test"
GENERIC = "Invalid email or password"


def login(client: TestClient, password: str, email: str = ANA) -> tuple[int, str]:
    response = client.post("/auth/login", data={"username": email, "password": password})
    message = response.json().get("error", {}).get("message", "")
    return response.status_code, message


def test_db27_five_wrong_passwords_lock_the_account(client: TestClient) -> None:
    for _ in range(5):
        assert login(client, "wrong-password") == (401, GENERIC)

    # The right password is now refused too, with exactly the same answer (no "locked" hint).
    assert login(client, PASSWORD) == (401, GENERIC)
    account = client.app.state.leavedesk.users.find_by_email(ANA)  # type: ignore[attr-defined]
    assert account.failed_login_count == 5
    assert account.locked_until is not None


def test_four_wrong_passwords_do_not_lock_and_success_resets_the_count(
    client: TestClient,
) -> None:
    for _ in range(4):
        assert login(client, "wrong-password")[0] == 401
    assert login(client, PASSWORD)[0] == 200
    account = client.app.state.leavedesk.users.find_by_email(ANA)  # type: ignore[attr-defined]
    assert (account.failed_login_count, account.locked_until) == (0, None)


def test_db28_login_works_again_after_the_lock_expires(client: TestClient) -> None:
    users = client.app.state.leavedesk.users  # type: ignore[attr-defined]
    twenty_minutes_ago = datetime.now(UTC) - timedelta(minutes=20)
    for _ in range(5):  # lock it 20 minutes ago, so the 15-minute lock has already expired
        users.record_failed_login("E-ANA", max_attempts=5, lock_minutes=15, now=twenty_minutes_ago)
    assert users.find_by_email(ANA).locked_until < datetime.now(UTC)

    assert login(client, PASSWORD)[0] == 200
    assert users.find_by_email(ANA).failed_login_count == 0


def test_lockout_is_per_account(client: TestClient) -> None:
    for _ in range(5):
        login(client, "wrong-password")
    assert login(client, PASSWORD, email="mo@leavedesk.test")[0] == 200
