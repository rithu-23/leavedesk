"""Request-ID middleware: tags every request and logs method, path, status and duration."""

import logging
import re
import time
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("leavedesk.api")

# Only accept simple incoming ids, so nothing odd can be injected into the logs.
_SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9-]{1,64}")


class RequestIdMiddleware:
    """Plain ASGI middleware, so it works with streaming responses (SSE) too."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get("x-request-id", "")
        request_id = incoming if _SAFE_REQUEST_ID.fullmatch(incoming) else uuid4().hex[:16]
        scope.setdefault("state", {})["request_id"] = request_id
        status_code = 500
        start = time.perf_counter()

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message).append("X-Request-ID", request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            # scope["path"] has no query string, so ?access_token=... never reaches the logs.
            logger.info(
                "request_id=%s method=%s path=%s status=%s duration_ms=%.2f",
                request_id,
                scope["method"],
                scope["path"],
                status_code,
                (time.perf_counter() - start) * 1000,
            )
