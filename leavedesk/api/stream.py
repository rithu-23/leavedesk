"""Live notifications over Server-Sent Events (API_SPEC.md section 6)."""

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator

from fastapi import Request

from leavedesk.api.schemas import NotificationOut
from leavedesk.domain.models import Notification
from leavedesk.domain.notifications import Notifier

KEEPALIVE_SECONDS = 15.0


class NotificationBroker:
    """One queue per open stream; each new notification goes to its recipient's queues."""

    def __init__(self) -> None:
        self._queues: defaultdict[str, set[asyncio.Queue[Notification]]] = defaultdict(set)

    def subscribe(self, recipient_id: str) -> asyncio.Queue[Notification]:
        queue: asyncio.Queue[Notification] = asyncio.Queue()
        self._queues[recipient_id].add(queue)
        return queue

    def unsubscribe(self, recipient_id: str, queue: asyncio.Queue[Notification]) -> None:
        self._queues[recipient_id].discard(queue)
        if not self._queues[recipient_id]:
            del self._queues[recipient_id]

    def publish(self, notification: Notification) -> int:
        """Hand the notification to every open stream of its recipient; return how many."""
        queues = self._queues.get(notification.recipient_id, set())
        for queue in queues:
            queue.put_nowait(notification)
        return len(queues)


class StreamNotifier(Notifier):
    """The in-app channel for the API: pushes notifications to open SSE streams."""

    channel = "in_app_stream"

    def __init__(self, broker: NotificationBroker) -> None:
        super().__init__()
        self._broker = broker

    async def deliver(self, notification: Notification) -> None:
        self._broker.publish(notification)


def format_sse(notification: Notification) -> str:
    data = NotificationOut.from_domain(notification).model_dump_json()
    return f"event: notification\ndata: {data}\n\n"


async def event_stream(
    broker: NotificationBroker,
    recipient_id: str,
    request: Request,
    keepalive_seconds: float = KEEPALIVE_SECONDS,
) -> AsyncIterator[str]:
    """Yield SSE messages until the client disconnects."""
    queue = broker.subscribe(recipient_id)
    try:
        yield ": connected\n\n"
        while not await request.is_disconnected():
            try:
                notification = await asyncio.wait_for(queue.get(), timeout=keepalive_seconds)
            except TimeoutError:
                yield ": keep-alive\n\n"  # lines starting with ':' are comments in SSE
            else:
                yield format_sse(notification)
    finally:
        broker.unsubscribe(recipient_id, queue)
