"""Notification delivery (BR-7, FR-9).

Notifier is an abstract base class: send() simulates network delay, calls the
subclass's deliver(), and logs the result (the template method pattern again).
EmailNotifier is a stub that records instead of emailing; InAppNotifier puts
notifications into each recipient's in-app inbox.

send_all() delivers every notification through every notifier concurrently
with asyncio.gather. A failed send is logged and counted but never stops the
others (AC-9.4).
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar

from leavedesk.domain.models import Notification

logger = logging.getLogger("leavedesk.notifications")


class Notifier(ABC):
    """Base class for every delivery channel."""

    channel: ClassVar[str]

    def __init__(self, delay_seconds: float = 0.0) -> None:
        # Simulated network time per send, used to demonstrate concurrency (AC-9.2).
        self._delay_seconds = delay_seconds

    async def send(self, notification: Notification) -> None:
        """Wait for the simulated network, deliver, then log."""
        await asyncio.sleep(self._delay_seconds)
        await self.deliver(notification)
        logger.info(
            "sent channel=%s recipient=%s event=%s",
            self.channel,
            notification.recipient_id,
            notification.event,
        )

    @abstractmethod
    async def deliver(self, notification: Notification) -> None:
        """Each channel delivers in its own way."""


class EmailNotifier(Notifier):
    """Stub email channel: records messages instead of contacting a mail server."""

    channel = "email"

    def __init__(self, delay_seconds: float = 0.0) -> None:
        super().__init__(delay_seconds)
        self.outbox: list[Notification] = []

    async def deliver(self, notification: Notification) -> None:
        # A real implementation would call an email service here.
        self.outbox.append(notification)


class InAppNotifier(Notifier):
    """In-app channel: keeps an inbox per recipient (Capstone 2 streams these over SSE)."""

    channel = "in_app"

    def __init__(self, delay_seconds: float = 0.0) -> None:
        super().__init__(delay_seconds)
        self.inboxes: defaultdict[str, list[Notification]] = defaultdict(list)

    async def deliver(self, notification: Notification) -> None:
        self.inboxes[notification.recipient_id].append(notification)


@dataclass(frozen=True)
class DeliveryReport:
    """How many sends succeeded and failed."""

    sent: int
    failed: int


async def send_all(
    notifications: Sequence[Notification], notifiers: Sequence[Notifier]
) -> DeliveryReport:
    """Send every notification through every notifier, all at the same time."""
    jobs = [(notifier, notification) for notification in notifications for notifier in notifiers]
    results = await asyncio.gather(
        *(notifier.send(notification) for notifier, notification in jobs),
        return_exceptions=True,
    )

    failed = 0
    for (notifier, notification), result in zip(jobs, results, strict=True):
        if isinstance(result, BaseException):
            failed += 1
            logger.error(
                "send failed channel=%s recipient=%s error=%s",
                notifier.channel,
                notification.recipient_id,
                type(result).__name__,
            )
    return DeliveryReport(sent=len(jobs) - failed, failed=failed)
