"""One error shape for every failure (API_SPEC.md section 5)."""

import logging
from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError
from starlette.exceptions import HTTPException as StarletteHTTPException

from leavedesk.api.security import AuthenticationError
from leavedesk.domain.exceptions import (
    ConcurrentUpdateError,
    DatabaseBusyError,
    IdempotencyKeyReusedError,
    InsufficientBalanceError,
    InvalidLeaveRequestError,
    InvalidTransitionError,
    LeaveDeskError,
    NotAuthorisedError,
    NotFoundError,
    OverlappingLeaveError,
)

logger = logging.getLogger("leavedesk.api")

# Day 1 domain errors -> (HTTP status, error code), as in API_SPEC.md section 5.
DOMAIN_ERRORS: list[tuple[type[LeaveDeskError], int, str]] = [
    (OverlappingLeaveError, 409, "OVERLAPPING_LEAVE"),
    (InvalidTransitionError, 409, "INVALID_TRANSITION"),
    (ConcurrentUpdateError, 409, "CONCURRENT_UPDATE"),  # Capstone 3 (API_SPEC v1.1)
    (InsufficientBalanceError, 422, "INSUFFICIENT_BALANCE"),
    (InvalidLeaveRequestError, 422, "INVALID_LEAVE_REQUEST"),
    (IdempotencyKeyReusedError, 422, "IDEMPOTENCY_KEY_REUSED"),  # Capstone 3
    (NotAuthorisedError, 403, "FORBIDDEN"),
    (NotFoundError, 404, "NOT_FOUND"),
]

HTTP_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
}


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, str]] | None = None,
) -> JSONResponse:
    body = {
        "error": {
            "code": code,
            "message": message,
            "request_id": getattr(request.state, "request_id", None),
            "details": details,
        }
    }
    headers = {"WWW-Authenticate": "Bearer"} if status_code == 401 else None
    return JSONResponse(status_code=status_code, content=body, headers=headers)


def _details(errors: Sequence[Any]) -> list[dict[str, str]]:
    """Turn Pydantic errors into [{field, message}] without leaking input values."""
    details = []
    for error in errors:
        parts = [str(p) for p in error.get("loc", ()) if p not in ("body", "query", "path")]
        details.append({"field": ".".join(parts) or "request", "message": str(error.get("msg"))})
    return details


async def _domain_error(request: Request, exc: Exception) -> JSONResponse:
    for error_type, status_code, code in DOMAIN_ERRORS:
        if isinstance(exc, error_type):
            return error_response(request, status_code, code, str(exc))
    return error_response(request, 400, "BAD_REQUEST", str(exc))


async def _authentication_error(request: Request, exc: Exception) -> JSONResponse:
    return error_response(request, 401, "UNAUTHENTICATED", str(exc))


async def _request_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = exc.errors()
    if any(error.get("type") == "json_invalid" for error in errors):
        return error_response(request, 400, "BAD_REQUEST", "The request body is not valid JSON.")
    return error_response(
        request, 422, "VALIDATION_ERROR", "The request is invalid.", _details(errors)
    )


async def _model_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ValidationError)
    return error_response(
        request, 422, "VALIDATION_ERROR", "The request is invalid.", _details(exc.errors())
    )


async def _http_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = HTTP_CODES.get(exc.status_code, "HTTP_ERROR")
    message = exc.detail if isinstance(exc.detail, str) else code
    return error_response(request, exc.status_code, code, message)


# SQLSTATEs that mean "the database was too busy", not "the request was wrong" (SCHEMA.md 6).
BUSY_SQLSTATES = {
    "55P03",  # lock_not_available: waited longer than lock_timeout (2 s)
    "57014",  # query_canceled: ran longer than statement_timeout (5 s)
    "40P01",  # deadlock_detected: should not happen (fixed lock order), but is safe to retry
}


def _busy_response(request: Request) -> JSONResponse:
    response = error_response(
        request,
        503,
        "DATABASE_BUSY",
        "The database is busy right now; nothing was saved. Please try again.",
    )
    response.headers["Retry-After"] = "1"
    return response


async def _database_busy(request: Request, exc: Exception) -> JSONResponse:
    return _busy_response(request)


async def _database_error(request: Request, exc: Exception) -> JSONResponse:
    """A database error that reached the API. Busy -> 503; anything else is a bug -> 500.

    The SQL and its parameters are never put in the response (they could contain data);
    the full error goes to the log with the request id.
    """
    assert isinstance(exc, DBAPIError)
    if getattr(exc.orig, "sqlstate", None) in BUSY_SQLSTATES:
        logger.warning(
            "database busy request_id=%s sqlstate=%s",
            getattr(request.state, "request_id", None),
            getattr(exc.orig, "sqlstate", None),
        )
        return _busy_response(request)
    return await _unexpected_error(request, exc)


async def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error request_id=%s", getattr(request.state, "request_id", None))
    return error_response(
        request,
        500,
        "INTERNAL_ERROR",
        "Something went wrong. Quote the request id if reporting it.",
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DatabaseBusyError, _database_busy)
    app.add_exception_handler(DBAPIError, _database_error)
    app.add_exception_handler(LeaveDeskError, _domain_error)
    app.add_exception_handler(AuthenticationError, _authentication_error)
    app.add_exception_handler(RequestValidationError, _request_validation_error)
    app.add_exception_handler(ValidationError, _model_validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unexpected_error)
