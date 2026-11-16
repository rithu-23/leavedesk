"""FastAPI dependencies: shared state, storage, the signed-in employee, the service, role checks."""

from collections.abc import AsyncIterator, Sequence
from typing import Annotated

from fastapi import BackgroundTasks, Depends, Query, Request
from fastapi.security import OAuth2PasswordBearer

from leavedesk.api.security import AuthenticationError, decode_access_token
from leavedesk.api.state import AppState
from leavedesk.db.outbox import deliver_pending
from leavedesk.db.repository import PostgresLeaveRepository
from leavedesk.domain.exceptions import NotAuthorisedError, NotFoundError
from leavedesk.domain.inbox import Inbox
from leavedesk.domain.models import Employee, Notification
from leavedesk.domain.notifications import Notifier, send_all
from leavedesk.domain.repository import LeaveRepository
from leavedesk.domain.service import LeaveService

# auto_error=False: we raise our own AuthenticationError, so 401s use the error contract.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_app_state(request: Request) -> AppState:
    state: AppState = request.app.state.leavedesk
    return state


StateDep = Annotated[AppState, Depends(get_app_state)]


async def get_repository(state: StateDep) -> AsyncIterator[LeaveRepository]:
    """Storage for one request: one unit of work (SPEC BR-10, SCHEMA.md 7).

    PostgreSQL mode: a new session and transaction per request. If the route
    raises, the exception passes back through this `yield`, `session.begin()`
    rolls everything back, and the error handlers build the response. If it
    succeeds, leaving `session.begin()` commits.

    scope="function" (see RepoDep) makes this code run when the route function
    returns, BEFORE the response is sent. So a client never receives 201 for a
    change that later fails to commit, and a follow-up request always sees it.
    """
    if state.session_factory is None or state.tenant_pk is None:
        assert state.repository is not None
        yield state.repository  # in-memory mode: nothing to open or commit
        return
    async with state.session_factory() as session, session.begin():
        yield PostgresLeaveRepository(session, state.tenant_pk)


# Every dependency in a request that asks for RepoDep gets the same repository
# (FastAPI caches it per request), so authentication and the action share one transaction.
RepoDep = Annotated[LeaveRepository, Depends(get_repository, scope="function")]


async def _employee_from_token(
    token: str | None, state: AppState, repo: LeaveRepository
) -> Employee:
    if not token:
        raise AuthenticationError("Not authenticated.")
    data = decode_access_token(token, state.settings)
    try:
        return await repo.get_employee(data.employee_id)
    except NotFoundError as error:
        raise AuthenticationError("Invalid or expired token.") from error


async def get_current_employee(
    state: StateDep, repo: RepoDep, token: Annotated[str | None, Depends(oauth2_scheme)]
) -> Employee:
    return await _employee_from_token(token, state, repo)


async def get_stream_employee(
    state: StateDep,
    repo: RepoDep,
    token: Annotated[str | None, Depends(oauth2_scheme)],
    access_token: Annotated[str | None, Query()] = None,
) -> Employee:
    """Browsers' EventSource can't send headers, so the stream also accepts ?access_token=."""
    return await _employee_from_token(token or access_token, state, repo)


CurrentEmployee = Annotated[Employee, Depends(get_current_employee)]
StreamEmployee = Annotated[Employee, Depends(get_stream_employee)]


class BackgroundNotifier(Notifier):
    """Instead of sending now, queues one background task that sends after the response."""

    channel = "background-queue"

    def __init__(self, tasks: BackgroundTasks, notifiers: Sequence[Notifier]) -> None:
        super().__init__()
        self._tasks = tasks
        self._notifiers = notifiers
        self._pending: list[Notification] = []

    async def deliver(self, notification: Notification) -> None:
        if not self._pending:  # the first notification registers the task...
            self._tasks.add_task(send_all, self._pending, self._notifiers)
        self._pending.append(notification)  # ...and every one joins the same batch


class OutboxDrainNotifier(Notifier):
    """PostgreSQL mode: the notifications are already in the outbox (saved by the
    repository in this request's transaction). This only queues ONE background task
    that drains the outbox after the response, so after the commit (SPEC BR-12)."""

    channel = "outbox-drain"

    def __init__(self, tasks: BackgroundTasks, state: AppState) -> None:
        super().__init__()
        self._tasks = tasks
        self._state = state
        self._queued = False

    async def deliver(self, notification: Notification) -> None:
        if self._queued:
            return
        assert self._state.session_factory is not None and self._state.tenant_pk is not None
        self._tasks.add_task(
            deliver_pending,
            self._state.session_factory,
            self._state.tenant_pk,
            self._state.notifiers,
        )
        self._queued = True


def get_service(state: StateDep, repo: RepoDep, background_tasks: BackgroundTasks) -> LeaveService:
    """A LeaveService for this request whose notifications are sent in the background.

    Background tasks run after the response, so in PostgreSQL mode they run
    after the commit: nobody is told about a change that was rolled back.
    In-memory mode sends directly; PostgreSQL mode drains the transactional outbox.
    """
    notifier: Notifier = (
        BackgroundNotifier(background_tasks, state.notifiers)
        if state.session_factory is None
        else OutboxDrainNotifier(background_tasks, state)
    )
    return LeaveService(repo, state.policies, notifiers=[notifier], clock=state.clock)


ServiceDep = Annotated[LeaveService, Depends(get_service)]


def get_inbox(repo: RepoDep) -> Inbox:
    return Inbox(repo)


InboxDep = Annotated[Inbox, Depends(get_inbox)]


def ensure_self_or_manager(actor: Employee, target: Employee) -> None:
    """Allow the person themselves, or their direct manager (API_SPEC.md section 3)."""
    if actor.id == target.id:
        return
    if actor.is_manager and target.manager_id == actor.id:
        return
    raise NotAuthorisedError(f"{actor.id} may not access data belonging to {target.id}.")
