"""Everything the API shares between requests, created once at start-up."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from leavedesk.api.settings import Settings
from leavedesk.api.stream import NotificationBroker
from leavedesk.api.users import UserDirectory
from leavedesk.domain.models import LeaveType
from leavedesk.domain.notifications import Notifier
from leavedesk.domain.policies import LeavePolicy
from leavedesk.domain.repository import LeaveRepository


@dataclass
class AppState:
    settings: Settings
    policies: Mapping[LeaveType, LeavePolicy]
    users: UserDirectory
    broker: NotificationBroker
    notifiers: Sequence[Notifier]  # the real channels, used by background tasks
    clock: Callable[[], date]
    # In-memory mode: one repository shared by every request.
    repository: LeaveRepository | None = None
    # PostgreSQL mode (DATABASE_URL set): a session per request, opened in deps.py.
    engine: AsyncEngine | None = None
    session_factory: async_sessionmaker[AsyncSession] | None = None
    tenant_pk: int | None = None  # internal id of settings.tenant_id, looked up at start-up
