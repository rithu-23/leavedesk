"""Everything the API shares between requests, created once at start-up."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from leavedesk.api.settings import Settings
from leavedesk.api.stream import NotificationBroker
from leavedesk.api.users import UserStore
from leavedesk.domain.models import LeaveType
from leavedesk.domain.notifications import Notifier
from leavedesk.domain.policies import LeavePolicy
from leavedesk.domain.repository import LeaveRepository


@dataclass
class AppState:
    settings: Settings
    repository: LeaveRepository
    policies: Mapping[LeaveType, LeavePolicy]
    users: UserStore
    broker: NotificationBroker
    notifiers: Sequence[Notifier]  # the real channels, used by background tasks
    clock: Callable[[], date]
