"""POST /auth/login."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.security import OAuth2PasswordRequestForm

from leavedesk.api.deps import RepoDep, StateDep
from leavedesk.api.schemas import TokenOut
from leavedesk.api.security import AuthenticationError, create_access_token, verify_password
from leavedesk.api.users import UserAccount, UserDirectory

router = APIRouter(prefix="/auth", tags=["auth"])

GENERIC_LOGIN_ERROR = "Invalid email or password"


def check_login(users: UserDirectory, email: str, password: str) -> UserAccount | None:
    """Look up the account and verify the password; None for any failure.

    Runs in FastAPI's thread pool: Argon2id is deliberately slow (tens of
    milliseconds of CPU) and the PostgreSQL account lookup is a blocking call,
    so neither may run on the event loop. Unknown emails still pay for one hash
    (verify_password with None uses a dummy hash), so response times don't reveal
    which emails exist.
    """
    account = users.find_by_email(email)
    password_ok = verify_password(password, account.password_hash if account else None)
    return account if account is not None and password_ok else None


@router.post("/login")
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], state: StateDep, repo: RepoDep
) -> TokenOut:
    """Form fields: username (the email) and password. Same error for any failure (API-2, API-3)."""
    account = await run_in_threadpool(check_login, state.users, form.username, form.password)
    if account is None:
        raise AuthenticationError(GENERIC_LOGIN_ERROR)
    employee = await repo.get_employee(account.employee_id)
    token, expires_in = create_access_token(employee.id, employee.role, state.settings)
    return TokenOut(access_token=token, expires_in=expires_in)
