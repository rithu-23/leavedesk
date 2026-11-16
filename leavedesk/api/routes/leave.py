"""Balance and leave-request endpoints (API_SPEC.md section 3)."""

import hashlib
import json
from typing import Annotated, Literal

from fastapi import APIRouter, Header, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from leavedesk.api.deps import CurrentEmployee, RepoDep, ServiceDep, ensure_self_or_manager
from leavedesk.api.schemas import BalanceOut, LeaveRequestCreate, LeaveRequestOut, Page, RejectBody
from leavedesk.domain.exceptions import IdempotencyKeyReusedError, NotAuthorisedError
from leavedesk.domain.models import LeaveStatus
from leavedesk.domain.repository import StoredResponse

router = APIRouter(tags=["leave"])


@router.get("/employees/{employee_id}/balance")
async def get_balance(
    employee_id: str, me: CurrentEmployee, repo: RepoDep, service: ServiceDep
) -> list[BalanceOut]:
    target = await repo.get_employee(employee_id)  # 404 first
    ensure_self_or_manager(me, target)  # then 403
    balances = await service.get_balances(target.id)
    return [BalanceOut.from_domain(b) for b in balances.values()]


# Idempotency-Key (API_SPEC v1.1): 1-255 visible ASCII characters, chosen by the client.
IdempotencyKey = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        pattern=r"^[\x21-\x7E]{1,255}$",
        description="Optional. Repeat a submit safely: the same key and body return the first result.",
    ),
]


def request_fingerprint(body: LeaveRequestCreate) -> str:
    """SHA-256 of the body in a fixed form (sorted keys), to tell 'same request' from 'different'."""
    canonical = json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


@router.post("/leave-requests", status_code=201, response_model=LeaveRequestOut)
async def apply_for_leave(
    body: LeaveRequestCreate,
    me: CurrentEmployee,
    service: ServiceDep,
    repo: RepoDep,
    idempotency_key: IdempotencyKey = None,
) -> LeaveRequestOut | JSONResponse:
    """Submit a request. With an Idempotency-Key, a retry never creates a second request.

    Same key + same body  -> the first response again, with Idempotent-Replayed: true (DB-17).
    Same key + other body -> 422 IDEMPOTENCY_KEY_REUSED (DB-18).
    A submit that fails is rolled back with its key, so it can be retried (DB-19).
    """
    fingerprint = request_fingerprint(body)
    if idempotency_key is not None:
        stored = await repo.claim_idempotency_key(me.id, idempotency_key)
        if stored is not None:
            if stored.request_hash != fingerprint:
                raise IdempotencyKeyReusedError(idempotency_key)
            return JSONResponse(
                status_code=stored.status,
                content=stored.body,
                headers={"Idempotent-Replayed": "true"},
            )

    request = await service.apply(
        me.id, body.leave_type, body.start_date, body.end_date, body.reason, body.half_day
    )
    created = LeaveRequestOut.from_domain(request)
    if idempotency_key is not None:
        await repo.save_idempotency_key(
            me.id,
            idempotency_key,
            StoredResponse(fingerprint, 201, created.model_dump(mode="json")),
            request.id,
        )
    return created


@router.get("/leave-requests")
async def list_leave_requests(
    me: CurrentEmployee,
    repo: RepoDep,
    status_filter: Annotated[LeaveStatus | None, Query(alias="status")] = None,
    employee_id: str | None = None,
    sort: Literal["start_date", "-start_date"] = "start_date",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> Page[LeaveRequestOut]:
    """Paginated in storage (API_SPEC 3.1): pass the previous page's next_cursor as
    ?cursor= for keyset pagination; plain offset still works as in v1.0."""
    if cursor is not None and offset > 0:
        raise _query_error("cursor", "Use either cursor or offset, not both.")
    reports = {e.id for e in await repo.list_employees() if e.manager_id == me.id}
    visible = {me.id} | reports
    if employee_id is not None:
        if employee_id not in visible:
            raise NotAuthorisedError(f"{me.id} may not list requests of {employee_id}.")
        visible = {employee_id}

    try:
        page = await repo.page_requests(
            employee_ids=visible,
            status=status_filter,
            descending=sort == "-start_date",
            limit=limit,
            offset=offset,
            cursor=cursor,
        )
    except ValueError as error:
        raise _query_error("cursor", "Invalid cursor.") from error
    return Page(
        items=[LeaveRequestOut.from_domain(r) for r in page.items],
        total=page.total,
        limit=limit,
        offset=0 if cursor is not None else offset,
        next_cursor=page.next_cursor,
    )


def _query_error(field: str, message: str) -> RequestValidationError:
    """Reported like any other invalid query parameter: 422 VALIDATION_ERROR."""
    return RequestValidationError(
        [{"loc": ("query", field), "msg": message, "type": "value_error"}]
    )


@router.get("/leave-requests/{request_id}")
async def get_leave_request(request_id: str, me: CurrentEmployee, repo: RepoDep) -> LeaveRequestOut:
    request = await repo.get_request(request_id)
    ensure_self_or_manager(me, await repo.get_employee(request.employee_id))
    return LeaveRequestOut.from_domain(request)


# If-Match (API_SPEC v1.1): the version the client last saw, as a plain integer;
# quotes are allowed because HTTP clients often quote ETag-style values.
IfMatch = Annotated[
    str | None,
    Header(
        alias="If-Match",
        pattern=r'^"?[1-9][0-9]{0,8}"?$',
        description="Optional. The request's `version`; 409 CONCURRENT_UPDATE if it changed.",
    ),
]


def expected_version(if_match: str | None) -> int | None:
    return int(if_match.strip('"')) if if_match is not None else None


@router.post("/leave-requests/{request_id}/approve")
async def approve_leave(
    request_id: str, me: CurrentEmployee, service: ServiceDep, if_match: IfMatch = None
) -> LeaveRequestOut:
    approved = await service.approve(request_id, me.id, expected_version=expected_version(if_match))
    return LeaveRequestOut.from_domain(approved)


@router.post("/leave-requests/{request_id}/reject")
async def reject_leave(
    request_id: str,
    body: RejectBody,
    me: CurrentEmployee,
    service: ServiceDep,
    if_match: IfMatch = None,
) -> LeaveRequestOut:
    rejected = await service.reject(
        request_id, me.id, body.reason, expected_version=expected_version(if_match)
    )
    return LeaveRequestOut.from_domain(rejected)


@router.delete("/leave-requests/{request_id}")
async def cancel_leave(
    request_id: str, me: CurrentEmployee, service: ServiceDep, if_match: IfMatch = None
) -> LeaveRequestOut:
    cancelled = await service.cancel(request_id, me.id, expected_version=expected_version(if_match))
    return LeaveRequestOut.from_domain(cancelled)
