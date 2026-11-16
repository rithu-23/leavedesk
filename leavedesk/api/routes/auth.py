"""POST /auth/login."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.security import OAuth2PasswordRequestForm

from leavedesk.api.deps import StateDep
from leavedesk.api.schemas import TokenOut
from leavedesk.api.security import AuthenticationError, create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

GENERIC_LOGIN_ERROR = "Invalid email or password"


@router.post("/login")
async def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], state: StateDep) -> TokenOut:
    """Form fields: username (the email) and password. Same error for any failure (API-2, API-3).

    Argon2id is deliberately slow (tens of milliseconds of CPU). Inside an async
    route that would freeze the event loop for every other request, so the
    check runs in FastAPI's thread pool instead.
    """
    account = state.users.find_by_email(form.username)
    password_ok = await run_in_threadpool(
        verify_password, form.password, account.password_hash if account else None
    )
    if account is None or not password_ok:
        raise AuthenticationError(GENERIC_LOGIN_ERROR)
    employee = await state.repository.get_employee(account.employee_id)
    token, expires_in = create_access_token(employee.id, employee.role, state.settings)
    return TokenOut(access_token=token, expires_in=expires_in)
