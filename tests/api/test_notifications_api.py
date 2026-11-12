"""API-22 to API-26 and background sending (API-6)."""

from fastapi import BackgroundTasks
from fastapi.testclient import TestClient

from leavedesk.api.deps import BackgroundNotifier
from leavedesk.api.stream import NotificationBroker, StreamNotifier, format_sse
from leavedesk.domain.models import Notification, NotificationEvent
from tests.api.support import RecordingNotifier, apply, error_code

Headers = dict[str, str]


def make_notification(recipient_id: str) -> Notification:
    return Notification(
        recipient_id=recipient_id, event=NotificationEvent.SUBMITTED, message="Ana requested leave."
    )


async def test_notifications_are_queued_as_one_background_task() -> None:  # API-6
    tasks = BackgroundTasks()
    recorder = RecordingNotifier()
    queue = BackgroundNotifier(tasks, [recorder])
    await queue.deliver(make_notification("E-ANA"))
    await queue.deliver(make_notification("E-MO"))
    assert len(tasks.tasks) == 1  # one task for the whole batch...
    assert recorder.sent == []  # ...and nothing sent before the response
    await tasks()  # what FastAPI does after sending the response
    assert sorted(n.recipient_id for n in recorder.sent) == ["E-ANA", "E-MO"]


def test_manager_sees_an_unread_submitted_notification(
    client: TestClient, ana: Headers, mo: Headers
) -> None:  # API-22
    apply(client, ana)
    for url in ("/notifications", "/notifications?unread=true"):
        body = client.get(url, headers=mo).json()
        assert body["total"] == 1
        assert body["items"][0]["event"] == "submitted"
        assert body["items"][0]["read"] is False


def test_mark_read_only_for_the_recipient(
    client: TestClient, ana: Headers, mo: Headers
) -> None:  # API-23
    apply(client, ana)
    notification_id = client.get("/notifications", headers=mo).json()["items"][0]["id"]
    response = client.post(f"/notifications/{notification_id}/read", headers=mo)
    assert response.status_code == 200
    assert response.json()["read"] is True
    stranger = client.post(f"/notifications/{notification_id}/read", headers=ana)
    assert stranger.status_code == 404
    assert error_code(stranger) == "NOT_FOUND"


def test_read_all_marks_everything_read(
    client: TestClient, ana: Headers, mo: Headers
) -> None:  # API-24
    apply(client, ana)
    apply(client, ana, start_date="2026-11-17", end_date="2026-11-17", half_day=True)
    response = client.post("/notifications/read-all", headers=mo)
    assert response.json() == {"updated": 2}
    assert client.get("/notifications?unread=true", headers=mo).json()["total"] == 0


def test_unread_notifications_come_first(client: TestClient, ana: Headers, mo: Headers) -> None:
    apply(client, ana)
    apply(client, ana, start_date="2026-11-17", end_date="2026-11-17", half_day=True)
    newest = client.get("/notifications", headers=mo).json()["items"][0]["id"]
    client.post(f"/notifications/{newest}/read", headers=mo)
    items = client.get("/notifications", headers=mo).json()["items"]
    assert [item["read"] for item in items] == [False, True]


async def test_stream_notifier_reaches_only_the_recipient() -> None:  # API-25
    broker = NotificationBroker()
    mo_stream = broker.subscribe("E-MO")
    ana_stream = broker.subscribe("E-ANA")
    await StreamNotifier(broker).deliver(make_notification("E-MO"))
    assert mo_stream.qsize() == 1
    assert ana_stream.qsize() == 0


def test_sse_message_format() -> None:
    notification = make_notification("E-MO")
    message = format_sse(notification)
    assert message.startswith("event: notification\ndata: {")
    assert notification.id in message
    assert message.endswith("\n\n")


def test_closed_streams_are_removed() -> None:
    broker = NotificationBroker()
    queue = broker.subscribe("E-MO")
    broker.unsubscribe("E-MO", queue)
    assert broker.publish(make_notification("E-MO")) == 0


def test_stream_requires_a_token(client: TestClient) -> None:  # API-26
    assert client.get("/notifications/stream").status_code == 401
    bad = client.get("/notifications/stream?access_token=not-a-real-token")
    assert bad.status_code == 401
    assert error_code(bad) == "UNAUTHENTICATED"
