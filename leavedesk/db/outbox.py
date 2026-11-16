"""Sending queued notifications from the transactional outbox (SPEC BR-12, SCHEMA.md 4.11).

Two callers, one function:
- the API's background task drains the outbox right after each response (fast path);
- the worker (leavedesk/worker.py) runs it in a loop, for anything left behind:
  a crash between commit and send, or a failed send waiting for its retry.

FOR UPDATE SKIP LOCKED is what lets them run side by side: a sender locks the
rows it claims, and any other sender simply skips locked rows instead of waiting
or taking them too. So two senders never send the same row (SPEC DB-24).

Delivery is at-least-once: if any channel fails, the row is retried later and
every channel gets it again. A row is given up (status 'failed') after
MAX_ATTEMPTS, and the leave action is never undone (SPEC BR-7).

Trade-off kept simple on purpose: rows stay locked while they are being sent,
inside one short transaction. Fine for fast channels (our email stub); with a slow
real email service we would mark rows 'sending' with a lease and commit first.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import joinedload

from leavedesk.db.models import NotificationOutboxRow, NotificationRow
from leavedesk.db.repository import PostgresLeaveRepository
from leavedesk.domain.notifications import Notifier, send_all

logger = logging.getLogger("leavedesk.outbox")

MAX_ATTEMPTS = 5
BATCH_SIZE = 50


@dataclass(frozen=True)
class OutboxRun:
    claimed: int
    sent: int
    retrying: int
    failed: int


def retry_delay(attempts: int) -> timedelta:
    """Exponential back-off: 2, 4, 8, 16 seconds after the 1st..4th failure."""
    return timedelta(seconds=2**attempts)


async def deliver_pending(
    session_factory: async_sessionmaker[AsyncSession],
    tenant_pk: int,
    notifiers: Sequence[Notifier],
    *,
    batch_size: int = BATCH_SIZE,
) -> OutboxRun:
    """Claim up to batch_size due rows, send them, record the outcome. One transaction."""
    sent = retrying = failed = 0
    async with session_factory() as session, session.begin():
        rows = (
            await session.scalars(
                select(NotificationOutboxRow)
                .options(
                    joinedload(NotificationOutboxRow.notification, innerjoin=True).joinedload(
                        NotificationRow.recipient, innerjoin=True
                    )
                )
                .where(
                    NotificationOutboxRow.tenant_id == tenant_pk,
                    NotificationOutboxRow.status == "pending",
                    NotificationOutboxRow.available_at <= func.now(),
                )
                .order_by(NotificationOutboxRow.available_at, NotificationOutboxRow.id)
                .limit(batch_size)
                # Lock only the outbox rows (not the joined ones), and skip rows that
                # another sender has already locked.
                .with_for_update(skip_locked=True, of=NotificationOutboxRow)
            )
        ).all()

        for row in rows:
            notification = PostgresLeaveRepository.to_notification(row.notification)
            report = await send_all([notification], notifiers)
            now = datetime.now(UTC)
            if report.failed == 0:
                row.status, row.sent_at, row.last_error = "sent", now, None
                sent += 1
                continue
            row.attempts += 1
            row.last_error = f"{report.failed} channel(s) failed"
            if row.attempts >= MAX_ATTEMPTS:
                row.status = "failed"
                failed += 1
                logger.error(
                    "outbox gave up notification=%s attempts=%s", notification.id, row.attempts
                )
            else:
                row.available_at = now + retry_delay(row.attempts)
                retrying += 1
    return OutboxRun(claimed=len(rows), sent=sent, retrying=retrying, failed=failed)
