"""Outbox worker: sends any notification the API's fast path did not (SPEC BR-12, DB-24).

    python -m leavedesk.worker            # runs until stopped (Ctrl+C)
    python -m leavedesk.worker --once     # one pass, then exit (handy in a demo)

The API already drains the outbox right after each response. This worker is the
safety net: notifications left behind by a crash between commit and send, and
failed sends waiting for their retry time. Several workers (and the API) can run
at once: FOR UPDATE SKIP LOCKED stops two of them sending the same row.
"""

import argparse
import asyncio
import logging

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import select

from leavedesk.db.engine import create_engine, create_session_factory
from leavedesk.db.models import TenantRow
from leavedesk.db.outbox import deliver_pending
from leavedesk.domain.notifications import EmailNotifier

logger = logging.getLogger("leavedesk.worker")


class WorkerSettings(BaseSettings):
    """Only what the worker needs (no JWT secret, no demo password)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    database_url: SecretStr
    tenant_id: str = "T-DEMO"
    log_level: str = "INFO"
    worker_poll_seconds: float = 2.0


async def run(settings: WorkerSettings, *, once: bool = False) -> None:
    engine = create_engine(settings.database_url.get_secret_value())
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session:
            tenant_pk = await session.scalar(
                select(TenantRow.id).where(TenantRow.public_id == settings.tenant_id)
            )
        if tenant_pk is None:
            raise SystemExit(
                f"Tenant {settings.tenant_id!r} not found; run `alembic upgrade head`."
            )
        notifiers = [EmailNotifier()]
        logger.info("worker started tenant=%s", settings.tenant_id)
        while True:
            result = await deliver_pending(session_factory, tenant_pk, notifiers)
            if result.claimed:
                logger.info(
                    "outbox claimed=%s sent=%s retrying=%s failed=%s",
                    result.claimed,
                    result.sent,
                    result.retrying,
                    result.failed,
                )
            if once:
                return
            if result.claimed == 0:  # nothing due: wait before looking again
                await asyncio.sleep(settings.worker_poll_seconds)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="LeaveDesk notification outbox worker")
    parser.add_argument("--once", action="store_true", help="run one pass and exit")
    args = parser.parse_args()
    settings = WorkerSettings()  # type: ignore[call-arg]
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(run(settings, once=args.once))


if __name__ == "__main__":
    main()
