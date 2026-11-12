"""Balance and leave-request endpoints (API_SPEC.md section 3)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Query

from leavedesk.api.deps import CurrentEmployee, ServiceDep, StateDep, ensure_self_or_manager
from leavedesk.api.schemas import BalanceOut, LeaveRequestCreate, LeaveRequestOut, Page, RejectBody
from leavedesk.domain.exceptions import NotAuthorisedError
from leavedesk.domain.models import LeaveStatus

router = APIRouter(tags=["leave"])


@router.get("/employees/{employee_id}/balance")
def get_balance(
    employee_id: str, me: CurrentEmployee, state: StateDep, service: ServiceDep
) -> list[BalanceOut]:
    target = state.repository.get_employee(employee_id)  # 404 first
    ensure_self_or_manager(me, target)  # then 403
    return [BalanceOut.from_domain(b) for b in service.get_balances(target.id).values()]


@router.post("/leave-requests", status_code=201)
async def apply_for_leave(
    body: LeaveRequestCreate, me: CurrentEmployee, service: ServiceDep
) -> LeaveRequestOut:
    request = await service.apply(
        me.id, body.leave_type, body.start_date, body.end_date, body.reason, body.half_day
    )
    return LeaveRequestOut.from_domain(request)


@router.get("/leave-requests")
def list_leave_requests(
    me: CurrentEmployee,
    state: StateDep,
    status_filter: Annotated[LeaveStatus | None, Query(alias="status")] = None,
    employee_id: str | None = None,
    sort: Literal["start_date", "-start_date"] = "start_date",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[LeaveRequestOut]:
    reports = {e.id for e in state.repository.list_employees() if e.manager_id == me.id}
    visible = {me.id} | reports
    if employee_id is not None:
        if employee_id not in visible:
            raise NotAuthorisedError(f"{me.id} may not list requests of {employee_id}.")
        visible = {employee_id}

    items = [
        r for r in state.repository.list_requests(status=status_filter) if r.employee_id in visible
    ]
    items.sort(key=lambda r: r.start_date, reverse=sort == "-start_date")
    page = items[offset : offset + limit]
    return Page(
        items=[LeaveRequestOut.from_domain(r) for r in page],
        total=len(items),
        limit=limit,
        offset=offset,
    )


@router.get("/leave-requests/{request_id}")
def get_leave_request(request_id: str, me: CurrentEmployee, state: StateDep) -> LeaveRequestOut:
    request = state.repository.get_request(request_id)
    ensure_self_or_manager(me, state.repository.get_employee(request.employee_id))
    return LeaveRequestOut.from_domain(request)


@router.post("/leave-requests/{request_id}/approve")
async def approve_leave(
    request_id: str, me: CurrentEmployee, service: ServiceDep
) -> LeaveRequestOut:
    return LeaveRequestOut.from_domain(await service.approve(request_id, me.id))


@router.post("/leave-requests/{request_id}/reject")
async def reject_leave(
    request_id: str, body: RejectBody, me: CurrentEmployee, service: ServiceDep
) -> LeaveRequestOut:
    return LeaveRequestOut.from_domain(await service.reject(request_id, me.id, body.reason))


@router.delete("/leave-requests/{request_id}")
async def cancel_leave(
    request_id: str, me: CurrentEmployee, service: ServiceDep
) -> LeaveRequestOut:
    return LeaveRequestOut.from_domain(await service.cancel(request_id, me.id))
