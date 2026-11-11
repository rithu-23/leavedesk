"""Cross-cutting helpers for BR-8: the @audit decorator and the timed() context manager.

@audit logs every call to the function it wraps: the action name, the request
id, whether it succeeded or failed, and how long it took. It never swallows
errors: a failure is logged and then re-raised to the caller (AC-11.2).
"""

import functools
import inspect
import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, ParamSpec, TypeVar, cast

logger = logging.getLogger("leavedesk.audit")

P = ParamSpec("P")
R = TypeVar("R")


@dataclass
class Timer:
    """Filled in by timed() when the block finishes."""

    elapsed_ms: float = 0.0


@contextmanager
def timed(operation: str, *, log: bool = True) -> Iterator[Timer]:
    """Measure how long the `with` block takes, in milliseconds.

    Usage:
        with timed("load data") as timer:
            ...
        print(timer.elapsed_ms)
    """
    timer = Timer()
    start = time.perf_counter()
    try:
        yield timer
    finally:
        timer.elapsed_ms = (time.perf_counter() - start) * 1000
        if log:
            logger.info("timing operation=%s duration_ms=%.2f", operation, timer.elapsed_ms)


def _find_request_id(
    signature: inspect.Signature, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> str:
    """Return the value passed for a `request_id` parameter, or '-' if there is none."""
    try:
        bound = signature.bind_partial(*args, **kwargs)
    except TypeError:
        return "-"
    return str(bound.arguments.get("request_id", "-"))


def _log_success(action: str, request_id: str, result: Any, timer: Timer) -> None:
    # apply() has no request_id argument; it returns the new request, so use its id.
    result_id = getattr(result, "id", None) or request_id
    logger.info(
        "audit action=%s request_id=%s outcome=success duration_ms=%.2f",
        action, result_id, timer.elapsed_ms,
    )


def _log_failure(action: str, request_id: str, error: Exception, timer: Timer) -> None:
    logger.warning(
        "audit action=%s request_id=%s outcome=failed error=%s duration_ms=%.2f",
        action, request_id, type(error).__name__, timer.elapsed_ms,
    )


def audit(func: Callable[P, R]) -> Callable[P, R]:
    """Decorator that logs and times every call to `func` (BR-8, FR-11).

    Works on both normal functions and async functions.
    """
    signature = inspect.signature(func)
    action = func.__name__

    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            request_id = _find_request_id(signature, args, kwargs)
            timer = Timer()
            try:
                with timed(action, log=False) as timer:
                    result = await func(*args, **kwargs)
            except Exception as error:
                _log_failure(action, request_id, error, timer)
                raise
            _log_success(action, request_id, result, timer)
            return result

        return cast(Callable[P, R], async_wrapper)

    @functools.wraps(func)
    def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        request_id = _find_request_id(signature, args, kwargs)
        timer = Timer()
        try:
            with timed(action, log=False) as timer:
                result = func(*args, **kwargs)
        except Exception as error:
            _log_failure(action, request_id, error, timer)
            raise
        _log_success(action, request_id, result, timer)
        return result

    return sync_wrapper
