"""API-6 to API-21: leave requests and balances over HTTP."""

from fastapi.testclient import TestClient

from tests.api.support import RecordingNotifier, apply, error_code

Headers = dict[str, str]


# ---------------------------------------------------------------- applying


def test_apply_creates_a_pending_request_and_queues_notifications(
    client: TestClient, ana: Headers, notifier: RecordingNotifier
) -> None:  # API-6
    response = apply(client, ana)
    assert response.status_code == 201
    body = response.json()
    assert (body["status"], body["days"], body["employee_id"]) == ("pending", "3", "E-ANA")
    assert sorted(n.recipient_id for n in notifier.sent) == ["E-ANA", "E-MO"]


def test_employee_id_in_the_body_is_ignored(client: TestClient, ana: Headers) -> None:
    response = apply(client, ana, employee_id="E-MO")
    assert response.json()["employee_id"] == "E-ANA"


def test_overlapping_request_is_409(client: TestClient, ana: Headers) -> None:  # API-7
    apply(client, ana)
    response = apply(
        client,
        ana,
        leave_type="SICK",
        start_date="2026-11-13",
        end_date="2026-11-13",
        reason="Fever and cold",
    )
    assert response.status_code == 409
    assert error_code(response) == "OVERLAPPING_LEAVE"


def test_end_before_start_is_422_mentioning_end_date(client: TestClient, ana: Headers) -> None:
    response = apply(client, ana, start_date="2026-11-13", end_date="2026-11-11")  # API-8
    assert response.status_code == 422
    assert error_code(response) == "VALIDATION_ERROR"
    assert "end_date" in response.text


def test_insufficient_balance_is_422(client: TestClient, ana: Headers) -> None:  # API-9
    response = apply(client, ana, start_date="2026-11-16", end_date="2026-12-11")
    assert response.status_code == 422
    assert error_code(response) == "INSUFFICIENT_BALANCE"


def test_policy_violation_is_422(client: TestClient, ana: Headers) -> None:
    response = apply(client, ana, start_date="2026-11-06", end_date="2026-11-06")
    assert response.status_code == 422
    assert error_code(response) == "INVALID_LEAVE_REQUEST"


def test_unknown_leave_type_lists_the_field(client: TestClient, ana: Headers) -> None:
    response = apply(client, ana, leave_type="HOLIDAY")
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "leave_type"


def test_body_that_is_not_json_is_400(client: TestClient, ana: Headers) -> None:  # API-10
    response = client.post(
        "/leave-requests",
        content="this is not json",
        headers={**ana, "Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert error_code(response) == "BAD_REQUEST"


# ---------------------------------------------------------------- listing and viewing


def test_employee_sees_only_their_own_requests(
    client: TestClient, ana: Headers, mo: Headers
) -> None:  # API-11
    apply(client, ana)
    apply(client, mo)
    body = client.get("/leave-requests", headers=ana).json()
    assert body["total"] == 1
    assert {item["employee_id"] for item in body["items"]} == {"E-ANA"}
    assert client.get("/leave-requests?status=approved", headers=ana).json()["total"] == 0


def test_employee_cannot_list_someone_elses_requests(client: TestClient, ana: Headers) -> None:
    response = client.get("/leave-requests?employee_id=E-MO", headers=ana)  # API-12
    assert response.status_code == 403
    assert error_code(response) == "FORBIDDEN"


def test_manager_sees_reports_pending_requests(
    client: TestClient, ana: Headers, mo: Headers
) -> None:  # API-13
    request_id = apply(client, ana).json()["id"]
    body = client.get("/leave-requests?status=pending", headers=mo).json()
    assert request_id in {item["id"] for item in body["items"]}


def test_sorting_and_pagination(client: TestClient, ana: Headers) -> None:
    apply(client, ana)
    apply(client, ana, start_date="2026-11-17", end_date="2026-11-17", half_day=True)
    body = client.get("/leave-requests?sort=-start_date&limit=1", headers=ana).json()
    assert body["total"] == 2
    assert len(body["items"]) == 1
    assert body["items"][0]["start_date"] == "2026-11-17"


def test_limit_out_of_range_is_422(client: TestClient, ana: Headers) -> None:
    response = client.get("/leave-requests?limit=0", headers=ana)
    assert response.status_code == 422
    assert error_code(response) == "VALIDATION_ERROR"


def test_unknown_request_is_404(client: TestClient, ana: Headers) -> None:  # API-14
    response = client.get("/leave-requests/LR-NOPE", headers=ana)
    assert response.status_code == 404
    assert error_code(response) == "NOT_FOUND"


def test_unrelated_manager_cannot_view_a_request(
    client: TestClient, ana: Headers, lee: Headers
) -> None:  # API-15
    request_id = apply(client, ana).json()["id"]
    response = client.get(f"/leave-requests/{request_id}", headers=lee)
    assert response.status_code == 403


# ---------------------------------------------------------------- decisions


def test_manager_approves_and_balance_moves_to_used(
    client: TestClient, ana: Headers, mo: Headers
) -> None:  # API-16
    request_id = apply(client, ana).json()["id"]
    response = client.post(f"/leave-requests/{request_id}/approve", headers=mo)
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    balances = client.get("/employees/E-ANA/balance", headers=ana).json()
    annual = next(b for b in balances if b["leave_type"] == "ANNUAL")
    assert (annual["used"], annual["available"]) == ("3", "15")


def test_employee_cannot_approve(client: TestClient, ana: Headers) -> None:  # API-17
    request_id = apply(client, ana).json()["id"]
    response = client.post(f"/leave-requests/{request_id}/approve", headers=ana)
    assert response.status_code == 403
    assert error_code(response) == "FORBIDDEN"


def test_approving_twice_is_409(client: TestClient, ana: Headers, mo: Headers) -> None:  # API-18
    request_id = apply(client, ana).json()["id"]
    client.post(f"/leave-requests/{request_id}/approve", headers=mo)
    response = client.post(f"/leave-requests/{request_id}/approve", headers=mo)
    assert response.status_code == 409
    assert error_code(response) == "INVALID_TRANSITION"


def test_reject_needs_a_reason(client: TestClient, ana: Headers, mo: Headers) -> None:  # API-19
    request_id = apply(client, ana).json()["id"]
    url = f"/leave-requests/{request_id}/reject"
    assert client.post(url, json={}, headers=mo).status_code == 422
    assert client.post(url, json={"reason": "   "}, headers=mo).status_code == 422
    response = client.post(url, json={"reason": "Team deadline that week"}, headers=mo)
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["decision_note"] == "Team deadline that week"


def test_cancel_rules(client: TestClient, ana: Headers, mo: Headers) -> None:  # API-20
    request_id = apply(client, ana).json()["id"]
    url = f"/leave-requests/{request_id}"
    assert client.delete(url, headers=mo).status_code == 403
    response = client.delete(url, headers=ana)
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    again = client.delete(url, headers=ana)
    assert again.status_code == 409
    assert error_code(again) == "INVALID_TRANSITION"


# ---------------------------------------------------------------- balances


def test_balance_access_rules(
    client: TestClient, ana: Headers, mo: Headers, lee: Headers
) -> None:  # API-21
    own = client.get("/employees/E-ANA/balance", headers=ana)
    assert own.status_code == 200
    assert {b["leave_type"] for b in own.json()} == {"ANNUAL", "SICK", "CASUAL"}
    assert client.get("/employees/E-ANA/balance", headers=mo).status_code == 200
    assert client.get("/employees/E-ANA/balance", headers=lee).status_code == 403
    missing = client.get("/employees/E-NOBODY/balance", headers=mo)
    assert missing.status_code == 404
    assert error_code(missing) == "NOT_FOUND"
