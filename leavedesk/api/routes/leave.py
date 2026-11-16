"""Balance and leave-request endpoints (API_SPEC.md section 3)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Header, Query

from leavedesk.api.deps import CurrentEmployee, RepoDep, ServiceDep, ensure_self_or_manager
from leavedesk.api.schemas import BalanceOut, LeaveRequestCreate, LeaveRequestOut, Page, RejectBody
from leavedesk.domain.exceptions import NotAuthorisedError
from leavedesk.domain.models import LeaveStatus

router = APIRouter(tags=["leave"])


@router.get("/employees/{employee_id}/balance")
async def get_balance(
    employee_id: str, me: CurrentEmployee, repo: RepoDep, service: ServiceDep
) -> list[BalanceOut]:
    target = await repo.get_employee(employee_id)  # 404 first
    ensure_self_or_manager(me, target)  # then 403
    balances = await service.get_balances(target.id)
    return [BalanceOut.from_domain(b) for b in balances.values()]


@router.post("/leave-requests", status_code=201)
async def apply_for_leave(
    body: LeaveRequestCreate, me: CurrentEmployee, service: ServiceDep
) -> LeaveRequestOut:
    request = await service.apply(
        me.id, body.leave_type, body.start_date, body.end_date, body.reason, body.half_day
    )
    return LeaveRequestOut.from_domain(request)


@router.get("/leave-requests")
async def list_leave_requests(
    me: CurrentEmployee,
    repo: RepoDep,
    status_filter: Annotated[LeaveStatus | None, Query(alias="status")] = None,
    employee_id: str | None = None,
    sort: Literal["start_date", "-start_date"] = "start_date",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[LeaveRequestOut]:
    reports = {e.id for e in await repo.list_employees() if e.manager_id == me.id}
    visible = {me.id} | reports
    if employee_id is not None:
        if employee_id not in visible:
            raise NotAuthorisedError(f"{me.id} may not list requests of {employee_id}.")
        visible = {employee_id}

    items = [r for r in await repo.list_requests(status=status_filter) if r.employee_id in visible]
    items.sort(key=lambda r: r.start_date, reverse=sort == "-start_date")
    page = items[offset : offset + limit]
    return Page(
        items=[LeaveRequestOut.from_domain(r) for r in page],
        total=len(items),
        limit=limit,
        offset=offset,
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
