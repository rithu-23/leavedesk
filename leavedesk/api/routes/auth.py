"""POST /auth/login."""

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.security import OAuth2PasswordRequestForm

from leavedesk.api.deps import RepoDep, StateDep
from leavedesk.api.schemas import TokenOut
from leavedesk.api.security import AuthenticationError, create_access_token, verify_password
from leavedesk.api.settings import Settings
from leavedesk.api.users import UserAccount, UserDirectory

router = APIRouter(prefix="/auth", tags=["auth"])

GENERIC_LOGIN_ERROR = "Invalid email or password"

logger = logging.getLogger("leavedesk.auth")


def check_login(
    users: UserDirectory, email: str, password: str, settings: Settings, now: datetime
) -> UserAccount | None:
    """Look up the account, verify the password and apply the lockout; None for any failure.

    Runs in FastAPI's thread pool: Argon2id is deliberately slow (tens of
    milliseconds of CPU) and the PostgreSQL account calls block, so neither may
    run on the event loop.

    Every failure looks the same to the caller (SPEC BR-13): unknown email, wrong
    password and locked account all return None, and all pay for one hash
    (verify_password with None uses a dummy hash), so neither the message nor the
    response time reveals which emails exist or which accounts are locked.
    """
    account = users.find_by_email(email)
    password_ok = verify_password(password, account.password_hash if account else None)
    if account is None:
        return None
    if account.is_locked(now):
        return None  # even the right password; failures while locked don't extend the lock
    if not password_ok:
        just_locked = users.record_failed_login(
            account.employee_id,
            max_attempts=settings.login_max_attempts,
            lock_minutes=settings.login_lock_minutes,
            now=now,
        )
        if just_locked:
            logger.warning("account locked employee=%s", account.employee_id)
        return None
    users.record_successful_login(account.employee_id, now=now)
    return account


@router.post("/login")
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], state: StateDep, repo: RepoDep
) -> TokenOut:
    """Form fields: username (the email) and password. Same error for any failure (API-2, API-3)."""
    account = await run_in_threadpool(
        check_login, state.users, form.username, form.password, state.settings, datetime.now(UTC)
    )
    if account is None:
        raise AuthenticationError(GENERIC_LOGIN_ERROR)
    employee = await repo.get_employee(account.employee_id)
    token, expires_in = create_access_token(employee.id, employee.role, state.settings)
    return TokenOut(access_token=token, expires_in=expires_in)
