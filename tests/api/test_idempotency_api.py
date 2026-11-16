"""SPEC BR-11 / FR-15: Idempotency-Key on POST /leave-requests (DB-17 to DB-20).

Runs in both storage modes: in memory with `pytest`, on PostgreSQL with
scripts/pytest-postgres.sh. DB-21 (two at the same moment) is in tests/db.
"""

from fastapi.testclient import TestClient

Headers = dict[str, str]

TRIP = {
    "leave_type": "ANNUAL",
    "start_date": "2026-11-11",
    "end_date": "2026-11-13",
    "reason": "Family trip to Ooty",
}


def submit(client: TestClient, headers: Headers, key: str | None, body: dict[str, str] = TRIP):
    extra = {"Idempotency-Key": key} if key is not None else {}
    return client.post("/leave-requests", json=body, headers={**headers, **extra})


def annual_pending(client: TestClient, headers: Headers) -> str:
    balances = client.get("/employees/E-ANA/balance", headers=headers).json()
    return str(next(b for b in balances if b["leave_type"] == "ANNUAL")["pending"])


def test_db17_repeat_with_the_same_key_returns_the_first_result(
    client: TestClient, ana: Headers
) -> None:
    first = submit(client, ana, "k-1")
    again = submit(client, ana, "k-1")

    assert (first.status_code, again.status_code) == (201, 201)
    assert again.json() == first.json()  # same id, same everything
    assert again.headers["idempotent-replayed"] == "true"
    assert "idempotent-replayed" not in first.headers
    assert client.get("/leave-requests", headers=ana).json()["total"] == 1
    assert annual_pending(client, ana) == "3"  # reserved once, not 6


def test_db18_same_key_with_a_different_body_is_refused(client: TestClient, ana: Headers) -> None:
    submit(client, ana, "k-1")
    other = {**TRIP, "start_date": "2026-11-16", "end_date": "2026-11-17"}

    response = submit(client, ana, "k-1", other)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert client.get("/leave-requests", headers=ana).json()["total"] == 1


def test_db19_a_failed_submit_stores_nothing_so_it_can_be_retried(
    client: TestClient, ana: Headers
) -> None:
    blocking = submit(client, ana, None).json()["id"]  # 11-13 Nov, no key
    clash = {**TRIP, "start_date": "2026-11-12"}
    assert submit(client, ana, "k-2", clash).status_code == 409  # overlap: rolled back

    assert client.delete(f"/leave-requests/{blocking}", headers=ana).status_code == 200
    retry = submit(client, ana, "k-2", clash)

    assert retry.status_code == 201
    assert "idempotent-replayed" not in retry.headers  # really created this time


def test_db20_keys_are_scoped_to_one_employee(
    client: TestClient, ana: Headers, mo: Headers
) -> None:
    anas = submit(client, ana, "shared-key")
    mos = submit(client, mo, "shared-key")
    assert (anas.status_code, mos.status_code) == (201, 201)
    assert anas.json()["id"] != mos.json()["id"]


def test_without_a_key_every_submit_is_new(client: TestClient, ana: Headers) -> None:
    first = submit(client, ana, None)
    second = submit(client, ana, None)  # same dates: refused as an overlap, not replayed
    assert first.status_code == 201
    assert second.status_code == 409


def test_invalid_keys_are_rejected(client: TestClient, ana: Headers) -> None:
    for bad in ("has space", "x" * 256):
        response = submit(client, ana, bad)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
