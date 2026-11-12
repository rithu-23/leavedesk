"""A person's notification inbox: list, mark one read, mark all read."""

from leavedesk.domain.exceptions import NotFoundError
from leavedesk.domain.models import Notification
from leavedesk.domain.repository import LeaveRepository


class Inbox:
    """Reads and updates notifications for one recipient at a time."""

    def __init__(self, repository: LeaveRepository) -> None:
        self._repo = repository

    def list(self, recipient_id: str, unread_only: bool = False) -> list[Notification]:
        """Unread first, newest first within each group."""
        items = self._repo.list_notifications(recipient_id)  # already newest first
        if unread_only:
            items = [n for n in items if not n.read]
        return sorted(items, key=lambda n: n.read)  # stable sort: False (unread) before True

    def mark_read(self, notification_id: str, recipient_id: str) -> Notification:
        """Someone else's notification is reported as not found, so ids can't be probed."""
        notification = self._repo.get_notification(notification_id)
        if notification.recipient_id != recipient_id:
            raise NotFoundError("Notification", notification_id)
        notification.read = True
        self._repo.save_notification(notification)
        return notification

    def mark_all_read(self, recipient_id: str) -> int:
        """Mark every unread notification read; return how many changed."""
        updated = 0
        for notification in self._repo.list_notifications(recipient_id):
            if not notification.read:
                notification.read = True
                self._repo.save_notification(notification)
                updated += 1
        return updated
