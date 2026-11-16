"""The async engine (connection pool) and the session factory.

One engine per process, created at start-up and disposed at shutdown. Each
HTTP request gets its own AsyncSession from the factory (one unit of work).
"""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    """Create the async engine.

    pool_pre_ping checks a pooled connection before handing it out, so a
    restarted database does not cause one failed request per stale connection.
    echo=True logs every SQL statement: used to spot N+1 queries (DB_ECHO=true).
    """
    return create_async_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5, echo=echo)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Sessions that keep loaded values after commit, so a response can be built from them."""
    return async_sessionmaker(engine, expire_on_commit=False)
