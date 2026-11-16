"""API_SPEC 3.1 / SPEC FR-18: keyset pagination on GET /leave-requests (DB-32 to DB-34).

Runs in both storage modes: in memory with `pytest`, on PostgreSQL with
scripts/pytest-postgres.sh (where the paging happens in SQL).
"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

Headers = dict[str, str]


def weekdays(start: date, count: int) -> list[date]:
    days, day = [], start
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def half_day(client: TestClient, headers: Headers, day: date, leave_type: str) -> str:
    response = client.post(
        "/leave-requests",
        json={
            "leave_type": leave_type,
            "start_date": day.isoformat(),
            "end_date": day.isoformat(),
            "half_day": True,
            "reason": "Half day for an appointment",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


@pytest.fixture
def forty_five(client: TestClient, ana: Headers) -> list[str]:
    """Ana's 45 requests: 36 annual and 9 sick half days on 45 different weekdays."""
    days = weekdays(date(2026, 11, 10), 45)
    return [half_day(client, ana, d, "ANNUAL" if i < 36 else "SICK") for i, d in enumerate(days)]


def walk(client: TestClient, headers: Headers, limit: int) -> list[list[str]]:
    pages, cursor = [], None
    while True:
        query = f"/leave-requests?limit={limit}" + (f"&cursor={cursor}" if cursor else "")
        body = client.get(query, headers=headers).json()
        pages.append([item["id"] for item in body["items"]])
        cursor = body["next_cursor"]
        if cursor is None:
            return pages


def test_db32_cursor_walk_returns_every_request_once_in_order(
    client: TestClient, ana: Headers, forty_five: list[str]
) -> None:
    pages = walk(client, ana, 20)
    assert [len(p) for p in pages] == [20, 20, 5]
    assert [i for page in pages for i in page] == forty_five  # created in date order


def test_descending_cursor_walk(client: TestClient, ana: Headers, forty_five: list[str]) -> None:
    pages, cursor = [], None
    while True:
        query = "/leave-requests?sort=-start_date&limit=20" + (
            f"&cursor={cursor}" if cursor else ""
        )
        body = client.get(query, headers=ana).json()
        pages.append([item["id"] for item in body["items"]])
        if (cursor := body["next_cursor"]) is None:
            break
    assert [i for page in pages for i in page] == list(reversed(forty_five))


def test_db33_a_new_earlier_request_does_not_shift_the_next_page(
    client: TestClient, ana: Headers, forty_five: list[str]
) -> None:
    first = client.get("/leave-requests?limit=20", headers=ana).json()
    half_day(client, ana, date(2026, 11, 6), "SICK")  # earlier than everything (sick may backdate)

    second = client.get(f"/leave-requests?limit=20&cursor={first['next_cursor']}", headers=ana)
    by_offset = client.get("/leave-requests?limit=20&offset=20", headers=ana)

    assert [i["id"] for i in second.json()["items"]] == forty_five[20:40]  # no repeat, no gap
    assert by_offset.json()["items"][0]["id"] == forty_five[19]  # OFFSET repeats a row


def test_db34_cursor_and_offset_together_is_422(
    client: TestClient, ana: Headers, forty_five: list[str]
) -> None:
    cursor = client.get("/leave-requests?limit=20", headers=ana).json()["next_cursor"]
    response = client.get(f"/leave-requests?cursor={cursor}&offset=20", headers=ana)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_invalid_cursor_is_422(client: TestClient, ana: Headers) -> None:
    response = client.get("/leave-requests?cursor=not-a-cursor", headers=ana)
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "cursor"


def test_last_page_has_no_next_cursor(client: TestClient, ana: Headers) -> None:
    half_day(client, ana, date(2026, 11, 10), "ANNUAL")
    body = client.get("/leave-requests", headers=ana).json()
    assert (body["total"], body["next_cursor"]) == (1, None)
