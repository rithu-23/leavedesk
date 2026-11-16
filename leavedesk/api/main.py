"""FastAPI application factory.

Run locally:  python -m uvicorn leavedesk.api.main:create_app --factory --reload
"""

import logging
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI

from leavedesk.api.errors import register_error_handlers
from leavedesk.api.middleware import RequestIdMiddleware
from leavedesk.api.routes import auth, leave, notifications
from leavedesk.api.settings import Settings, get_settings
from leavedesk.api.state import AppState
from leavedesk.api.stream import NotificationBroker, StreamNotifier
from leavedesk.api.users import UserStore, seed_demo_data
from leavedesk.domain.notifications import EmailNotifier, Notifier
from leavedesk.domain.policies import default_policies
from leavedesk.domain.repository import InMemoryLeaveRepository
from leavedesk.domain.service import LeaveService


def create_app(
    settings: Settings | None = None,
    *,
    clock: Callable[[], date] = date.today,
    notifiers: Sequence[Notifier] | None = None,
) -> FastAPI:
    """Build the app. Tests pass their own settings, clock and (mocked) notifiers."""
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    broker = NotificationBroker()
    state = AppState(
        settings=settings,
        repository=InMemoryLeaveRepository(),
        policies=default_policies(),
        users=UserStore(),
        broker=broker,
        notifiers=list(notifiers)
        if notifiers is not None
        else [EmailNotifier(), StreamNotifier(broker)],
        clock=clock,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """Runs once when the server starts (before the first request) and once when it stops.

        Seeding needs the async repository, so it can no longer run inside this
        plain (sync) factory function. uvicorn and `with TestClient(app)` both
        run the lifespan. Capstone 3 also opens and closes the database engine here.
        """
        await seed_demo_data(
            LeaveService(state.repository, state.policies, clock=clock),
            state.users,
            settings.demo_password.get_secret_value(),
        )
        yield

    app = FastAPI(
        title=settings.app_name,
        version="2.0.0",
        description="LeaveDesk REST API (Capstone 2). Use **Authorize** to sign in.",
        lifespan=lifespan,
    )
    app.state.leavedesk = state
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)
    app.include_router(auth.router)
    app.include_router(leave.router)
    app.include_router(notifications.router)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
