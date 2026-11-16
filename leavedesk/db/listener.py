"""LISTEN/NOTIFY feed for the live notification stream (SPEC BR-12, DB-25).

A trigger on the notifications table calls pg_notify('leavedesk_notifications', ...)
for every new row (revision 0002). PostgreSQL delivers that message only when the
inserting transaction COMMITS. This task keeps one connection LISTENing and, for each
message, loads the notification and hands it to the SSE broker: no polling loop.

It reconnects with a short pause if the connection drops (database restart).
"""

import asyncio
import json
import logging

import psycopg
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from leavedesk.api.stream import NotificationBroker
from leavedesk.db.repository import PostgresLeaveRepository
from leavedesk.domain.exceptions import NotFoundError

logger = logging.getLogger("leavedesk.listener")

CHANNEL = "leavedesk_notifications"


def libpq_url(sqlalchemy_url: str) -> str:
    return sqlalchemy_url.replace("postgresql+psycopg://", "postgresql://", 1)


async def listen_for_notifications(
    database_url: str,
    session_factory: async_sessionmaker[AsyncSession],
    tenant_pk: int,
    broker: NotificationBroker,
    *,
    ready: asyncio.Event | None = None,
) -> None:
    """Run until cancelled (the app's lifespan cancels it on shutdown)."""
    while True:
        try:
            async with await psycopg.AsyncConnection.connect(
                libpq_url(database_url), autocommit=True
            ) as connection:
                await connection.execute(f"LISTEN {CHANNEL}")
                logger.info("listening channel=%s", CHANNEL)
                if ready is not None:
                    ready.set()
                async for message in connection.notifies():
                    await _publish(message.payload, session_factory, tenant_pk, broker)
        except asyncio.CancelledError:
            raise
        except Exception:  # keep the stream alive across database restarts
            logger.exception("listener connection lost; reconnecting in 2 s")
            await asyncio.sleep(2)


async def _publish(
    payload: str,
    session_factory: async_sessionmaker[AsyncSession],
    tenant_pk: int,
    broker: NotificationBroker,
) -> None:
    data = json.loads(payload)
    if data.get("tenant_id") != tenant_pk:
        return
    async with session_factory() as session:
        try:
            notification = await PostgresLeaveRepository(session, tenant_pk).get_notification(
                data["id"]
            )
        except NotFoundError:
            return
    broker.publish(notification)
