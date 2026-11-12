"""Notification endpoints and the live SSE stream (API_SPEC.md section 3)."""

from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from leavedesk.api.deps import CurrentEmployee, InboxDep, StateDep, StreamEmployee
from leavedesk.api.schemas import NotificationOut, Page
from leavedesk.api.stream import event_stream

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
def list_notifications(
    me: CurrentEmployee,
    inbox: InboxDep,
    unread: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[NotificationOut]:
    items = inbox.list(me.id, unread_only=unread)
    page = items[offset : offset + limit]
    return Page(
        items=[NotificationOut.from_domain(n) for n in page],
        total=len(items),
        limit=limit,
        offset=offset,
    )


@router.post("/read-all")
def mark_all_read(me: CurrentEmployee, inbox: InboxDep) -> dict[str, int]:
    return {"updated": inbox.mark_all_read(me.id)}


@router.post("/{notification_id}/read")
def mark_read(notification_id: str, me: CurrentEmployee, inbox: InboxDep) -> NotificationOut:
    return NotificationOut.from_domain(inbox.mark_read(notification_id, me.id))


@router.get("/stream")
async def stream(request: Request, me: StreamEmployee, state: StateDep) -> StreamingResponse:
    """Server-Sent Events. Swagger can't display a live stream; use curl or a browser."""
    return StreamingResponse(
        event_stream(state.broker, me.id, request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
