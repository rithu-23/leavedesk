"""FastAPI dependencies: shared state, the signed-in employee, the service, role checks."""

from collections.abc import Sequence
from typing import Annotated

from fastapi import BackgroundTasks, Depends, Query, Request
from fastapi.security import OAuth2PasswordBearer

from leavedesk.api.security import AuthenticationError, decode_access_token
from leavedesk.api.state import AppState
from leavedesk.domain.exceptions import NotAuthorisedError, NotFoundError
from leavedesk.domain.inbox import Inbox
from leavedesk.domain.models import Employee, Notification
from leavedesk.domain.notifications import Notifier, send_all
from leavedesk.domain.service import LeaveService

# auto_error=False: we raise our own AuthenticationError, so 401s use the error contract.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_app_state(request: Request) -> AppState:
    state: AppState = request.app.state.leavedesk
    return state


StateDep = Annotated[AppState, Depends(get_app_state)]


def _employee_from_token(token: str | None, state: AppState) -> Employee:
    if not token:
        raise AuthenticationError("Not authenticated.")
    data = decode_access_token(token, state.settings)
    try:
        return state.repository.get_employee(data.employee_id)
    except NotFoundError as error:
        raise AuthenticationError("Invalid or expired token.") from error


def get_current_employee(
    state: StateDep, token: Annotated[str | None, Depends(oauth2_scheme)]
) -> Employee:
    return _employee_from_token(token, state)


def get_stream_employee(
    state: StateDep,
    token: Annotated[str | None, Depends(oauth2_scheme)],
    access_token: Annotated[str | None, Query()] = None,
) -> Employee:
    """Browsers' EventSource can't send headers, so the stream also accepts ?access_token=."""
    return _employee_from_token(token or access_token, state)


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


def get_service(state: StateDep, background_tasks: BackgroundTasks) -> LeaveService:
    """A LeaveService for this request whose notifications are sent in the background."""
    return LeaveService(
        state.repository,
        state.policies,
        notifiers=[BackgroundNotifier(background_tasks, state.notifiers)],
        clock=state.clock,
    )


ServiceDep = Annotated[LeaveService, Depends(get_service)]


def get_inbox(state: StateDep) -> Inbox:
    return Inbox(state.repository)


InboxDep = Annotated[Inbox, Depends(get_inbox)]


def ensure_self_or_manager(actor: Employee, target: Employee) -> None:
    """Allow the person themselves, or their direct manager (API_SPEC.md section 3)."""
    if actor.id == target.id:
        return
    if actor.is_manager and target.manager_id == actor.id:
        return
    raise NotAuthorisedError(f"{actor.id} may not access data belonging to {target.id}.")
