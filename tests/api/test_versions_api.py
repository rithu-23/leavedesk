"""API_SPEC v1.1: `version` on every request and the optional If-Match header (SPEC DB-12).

Runs in both storage modes: in memory with `pytest`, on PostgreSQL with
scripts/pytest-postgres.sh.
"""

from fastapi.testclient import TestClient

Headers = dict[str, str]

TRIP = {
    "leave_type": "ANNUAL",
    "start_date": "2026-11-11",
    "end_date": "2026-11-13",
    "reason": "Family trip to Ooty",
}


def test_new_request_starts_at_version_1(client: TestClient, ana: Headers) -> None:
    response = client.post("/leave-requests", json=TRIP, headers=ana)
    assert response.json()["version"] == 1


def test_db12_stale_if_match_is_refused_and_changes_nothing(
    client: TestClient, ana: Headers, mo: Headers
) -> None:
    request_id = client.post("/leave-requests", json=TRIP, headers=ana).json()["id"]

    response = client.post(f"/leave-requests/{request_id}/approve", headers={**mo, "If-Match": "2"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONCURRENT_UPDATE"
    unchanged = client.get(f"/leave-requests/{request_id}", headers=ana).json()
    assert (unchanged["status"], unchanged["version"]) == ("pending", 1)


def test_matching_if_match_succeeds_and_bumps_the_version(
    client: TestClient, ana: Headers, mo: Headers
) -> None:
    request_id = client.post("/leave-requests", json=TRIP, headers=ana).json()["id"]

    response = client.post(
        f"/leave-requests/{request_id}/approve", headers={**mo, "If-Match": '"1"'}
    )

    assert response.status_code == 200
    assert (response.json()["status"], response.json()["version"]) == ("approved", 2)


def test_if_match_works_on_cancel_too(client: TestClient, ana: Headers) -> None:
    request_id = client.post("/leave-requests", json=TRIP, headers=ana).json()["id"]
    stale = client.delete(f"/leave-requests/{request_id}", headers={**ana, "If-Match": "5"})
    assert stale.status_code == 409
    fresh = client.delete(f"/leave-requests/{request_id}", headers={**ana, "If-Match": "1"})
    assert fresh.status_code == 200


def test_if_match_must_be_a_positive_integer(client: TestClient, ana: Headers, mo: Headers) -> None:
    request_id = client.post("/leave-requests", json=TRIP, headers=ana).json()["id"]
    response = client.post(
        f"/leave-requests/{request_id}/approve", headers={**mo, "If-Match": "abc"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
