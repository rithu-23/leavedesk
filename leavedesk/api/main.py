"""FastAPI application factory.

Run locally:  python -m uvicorn leavedesk.api.main:create_app --factory --reload

Storage is chosen by settings.database_url:
- not set: in-memory repository (Capstone 2 behaviour, fast tests);
- set:     PostgreSQL through SQLAlchemy (Capstone 3). Run `alembic upgrade head` first.
"""

import logging
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select

from leavedesk.api.errors import register_error_handlers
from leavedesk.api.middleware import RequestIdMiddleware
from leavedesk.api.routes import auth, leave, notifications
from leavedesk.api.settings import Settings, get_settings
from leavedesk.api.state import AppState
from leavedesk.api.stream import NotificationBroker, StreamNotifier
from leavedesk.api.users import UserStore, seed_demo_employees, seed_demo_logins
from leavedesk.db.engine import create_engine, create_session_factory
from leavedesk.db.models import TenantRow
from leavedesk.db.repository import PostgresLeaveRepository
from leavedesk.db.users import PostgresUserStore
from leavedesk.domain.notifications import EmailNotifier, Notifier
from leavedesk.domain.policies import default_policies
from leavedesk.domain.repository import InMemoryLeaveRepository
from leavedesk.domain.service import LeaveService

logger = logging.getLogger("leavedesk.api")


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

        uvicorn and `with TestClient(app)` both run it. The database engine is
        created here, inside the running event loop, and closed on shutdown.
        """
        if settings.database_url is None:
            state.repository = InMemoryLeaveRepository()
            await seed_demo_employees(
                state.repository, LeaveService(state.repository, state.policies, clock=clock)
            )
            seed_demo_logins(state.users, settings.demo_password.get_secret_value())
            yield
            return

        url = settings.database_url.get_secret_value()
        state.engine = create_engine(url, echo=settings.db_echo)
        state.session_factory = create_session_factory(state.engine)
        try:
            async with state.session_factory() as session, session.begin():
                tenant_pk = await session.scalar(
                    select(TenantRow.id).where(TenantRow.public_id == settings.tenant_id)
                )
                if tenant_pk is None:
                    raise RuntimeError(
                        f"Tenant {settings.tenant_id!r} not found. Run `alembic upgrade head`."
                    )
                repository = PostgresLeaveRepository(session, tenant_pk)
                added = await seed_demo_employees(
                    repository, LeaveService(repository, state.policies, clock=clock)
                )
            state.tenant_pk = tenant_pk
            users = PostgresUserStore(url, tenant_pk)
            state.users = users
            # After the commit above, so the employees the logins point at exist.
            await run_in_threadpool(
                seed_demo_logins, users, settings.demo_password.get_secret_value()
            )
            logger.info(
                "storage=postgresql tenant=%s demo_data=%s",
                settings.tenant_id,
                "seeded" if added else "already present",
            )
            yield
        finally:
            if isinstance(state.users, PostgresUserStore):
                state.users.dispose()
            await state.engine.dispose()

    app = FastAPI(
        title=settings.app_name,
        version="3.0.0",
        description="LeaveDesk REST API (Capstone 3). Use **Authorize** to sign in.",
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
