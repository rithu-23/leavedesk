"""SPEC FR-16: notifications through the database (Part C2, "Done when" rollback test).

DB-22 outbox row in the same transaction   DB-23 rollback leaves nothing (and no NOTIFY)
DB-24 two workers never send the same row  DB-25 LISTEN/NOTIFY feeds the live stream
DB-26 failed sends are retried, then given up
"""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime

import psycopg
import pytest
from fastapi.testclient import TestClient

from leavedesk.api.stream import NotificationBroker
from leavedesk.db.listener import listen_for_notifications
from leavedesk.db.outbox import MAX_ATTEMPTS, deliver_pending
from leavedesk.db.repository import PostgresLeaveRepository
from leavedesk.domain.models import Notification, NotificationEvent
from leavedesk.domain.notifications import EmailNotifier, Notifier
from leavedesk.domain.policies import default_policies
from leavedesk.domain.service import LeaveService
from tests.api.support import RecordingNotifier, auth_headers
from tests.db.conftest import libpq_url
from tests.db.support import apply, nov, postgres_app, sessions
from tests.helpers import TODAY


@pytest.fixture
def client(app_database_url: str) -> Iterator[TestClient]:
    with postgres_app(app_database_url) as test_client:
        yield test_client


def query(database_url: str, sql: str) -> list[tuple[object, ...]]:
    with psycopg.connect(libpq_url(database_url)) as conn:
        return conn.execute(sql).fetchall()


async def add_notifications(database_url: str, count: int, recipient: str = "E-MO") -> list[str]:
    """Queue notifications directly (no API, so nothing drains them yet)."""
    async with (
        sessions(database_url) as (tenant_pk, factory),
        factory() as session,
        session.begin(),
    ):
        repo = PostgresLeaveRepository(session, tenant_pk)
        items = [
            Notification(recipient_id=recipient, event=NotificationEvent.SUBMITTED, message=f"#{i}")
            for i in range(count)
        ]
        for item in items:
            await repo.add_notification(item)
    return [item.id for item in items]


# ---------- DB-22 ----------


def test_db22_approval_stores_notification_and_outbox_row_together(
    client: TestClient, app_database_url: str
) -> None:
    ana = auth_headers(client, "ana@leavedesk.test")
    mo = auth_headers(client, "mo@leavedesk.test")
    request_id = apply(client, ana, nov(11), nov(13))
    assert client.post(f"/leave-requests/{request_id}/approve", headers=mo).status_code == 200

    rows = query(
        app_database_url,
        "SELECT n.event, o.status FROM notifications n "
        "JOIN notification_outbox o ON o.notification_id = n.id ORDER BY n.id",
    )
    # submitted -> Ana and Mo; approved -> Ana. Every notification has exactly one outbox
    # row, and the API's background task has already sent them all.
    assert rows == [("submitted", "sent"), ("submitted", "sent"), ("approved", "sent")]
    recorded = client.app.state.leavedesk.notifiers[0]  # type: ignore[attr-defined]
    assert isinstance(recorded, RecordingNotifier)


# ---------- DB-23: the "Done when" rollback test ----------


async def test_db23_rolled_back_approval_creates_no_notification(
    client: TestClient, app_database_url: str
) -> None:
    ana = auth_headers(client, "ana@leavedesk.test")
    request_id = apply(client, ana, nov(11), nov(13))
    before = query(app_database_url, "SELECT count(*) FROM notifications")[0][0]

    with psycopg.connect(libpq_url(app_database_url), autocommit=True) as listener:
        listener.execute("LISTEN leavedesk_notifications")

        async with sessions(app_database_url) as (tenant_pk, factory):
            with pytest.raises(RuntimeError, match="crash after the notifications were written"):
                async with factory() as session, session.begin():
                    service = LeaveService(
                        PostgresLeaveRepository(session, tenant_pk),
                        default_policies(),
                        clock=lambda: TODAY,
                    )
                    await service.approve(request_id, "E-MO")  # writes notification + outbox
                    raise RuntimeError("crash after the notifications were written")

        heard = list(listener.notifies(timeout=1.0))  # NOTIFY is only sent on commit

    assert heard == []
    assert query(app_database_url, "SELECT count(*) FROM notifications")[0][0] == before
    assert query(
        app_database_url, "SELECT count(*) FROM notifications WHERE event = 'approved'"
    ) == [(0,)]
    assert client.get(f"/leave-requests/{request_id}", headers=ana).json()["status"] == "pending"


# ---------- DB-24 ----------


async def test_db24_two_workers_never_send_the_same_row(
    client: TestClient, app_database_url: str
) -> None:
    queued = await add_notifications(app_database_url, 20)
    first, second = EmailNotifier(delay_seconds=0.01), EmailNotifier(delay_seconds=0.01)

    async with sessions(app_database_url) as (tenant_pk, factory):

        async def worker(notifier: Notifier) -> None:
            while (await deliver_pending(factory, tenant_pk, [notifier], batch_size=3)).claimed:
                pass

        await asyncio.gather(worker(first), worker(second))

    sent_ids = [n.id for n in first.outbox] + [n.id for n in second.outbox]
    assert sorted(sent_ids) == sorted(queued)  # every row once: none twice, none missed
    assert first.outbox and second.outbox  # both workers really took part
    assert query(app_database_url, "SELECT DISTINCT status FROM notification_outbox") == [("sent",)]


# ---------- DB-25 ----------


async def test_db25_committed_notification_reaches_the_stream_via_listen(
    client: TestClient, app_database_url: str
) -> None:
    broker = NotificationBroker()
    mo_stream = broker.subscribe("E-MO")
    ready = asyncio.Event()

    async with sessions(app_database_url) as (tenant_pk, factory):
        task = asyncio.create_task(
            listen_for_notifications(app_database_url, factory, tenant_pk, broker, ready=ready)
        )
        try:
            await asyncio.wait_for(ready.wait(), timeout=5)
            [queued] = await add_notifications(app_database_url, 1)  # commits
            received = await asyncio.wait_for(mo_stream.get(), timeout=2)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    assert received.id == queued


# ---------- DB-26 ----------


class BrokenEmail(Notifier):
    channel = "broken-email"

    async def deliver(self, notification: Notification) -> None:
        raise ConnectionError("mail server down")


async def test_db26_failed_send_is_retried_later_then_given_up(
    client: TestClient, app_database_url: str, migrator_database_url: str
) -> None:
    await add_notifications(app_database_url, 1)

    async with sessions(app_database_url) as (tenant_pk, factory):
        first = await deliver_pending(factory, tenant_pk, [BrokenEmail()])
        assert (first.claimed, first.retrying) == (1, 1)
        [(status, attempts, available_at)] = query(
            app_database_url, "SELECT status, attempts, available_at FROM notification_outbox"
        )
        assert (status, attempts) == ("pending", 1)
        assert available_at > datetime.now(UTC)  # not due again yet (back-off)
        assert (await deliver_pending(factory, tenant_pk, [BrokenEmail()])).claimed == 0

        # Pretend the back-off passed and this is the last allowed attempt.
        with psycopg.connect(libpq_url(migrator_database_url)) as conn:
            conn.execute(
                "UPDATE notification_outbox SET attempts = %s, available_at = now() - interval '1 s'",
                (MAX_ATTEMPTS - 1,),
            )
        last = await deliver_pending(factory, tenant_pk, [BrokenEmail()])

    assert last.failed == 1
    assert query(app_database_url, "SELECT status, attempts FROM notification_outbox") == [
        ("failed", MAX_ATTEMPTS)
    ]
