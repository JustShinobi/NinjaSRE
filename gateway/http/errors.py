"""No exception detail crosses the REST boundary (FR-004, SC-005).

Two families of failure reach a handler, and they are treated differently on
purpose.

**Named platform errors** — ``PersistenceError`` and ``PermissionDenied`` and
their subclasses — already carry a message written to be safe outside the
process (see their own module docstrings). Those are shown to the client
as-is, mapped to a status code.

**Everything else** is an exception nobody wrote a public sentence for: a
library's internals, a bug, a dependency's own error string, which routinely
contains a stack of arguments the caller never meant to publish. Those go
through ``SinkGuard.render_failure`` — at most the exception's type name — and
the full detail is logged server-side with the correlation id that ties the
two together.

``ApiProblem`` is what a route raises for a validation or state failure it
detected itself and already phrased safely; it is a third case only in that a
handler chooses its status code, not in how much detail crosses the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from gateway.http.correlation import correlation_id_of
from platform.config_service.errors import (
    ChangeRequiresApproval,
    ConfigInvalid,
    ConfigServiceError,
    FieldLocked,
    LockConflict,
    UnknownNode,
)
from platform.guardrails.engine import GuardrailEngine
from platform.guardrails.sinks import Sink, SinkGuard
from platform.identity.errors import PermissionDenied, TokenRejected
from platform.observability.logging import get_logger
from platform.persistence.errors import (
    BoundExceeded,
    ConcurrentModification,
    DuplicateRecord,
    PayloadTooLarge,
    PersistenceError,
    RecordNotFound,
    ReferencedRecord,
)

logger = get_logger(__name__)

#: The engine used to sanitise a failure nobody wrote a public sentence for.
#: One shared instance: the ruleset is immutable once loaded, and scanning a
#: type name never needs a run's masking context.
_GUARD = SinkGuard(engine=GuardrailEngine())


@dataclass(slots=True)
class ApiProblem(Exception):
    """A failure a route detected itself, with a status and a message already safe to show."""

    status_code: int
    message: str
    error_type: str = "bad_request"

    def __str__(self) -> str:
        return self.message


def bad_request(message: str) -> ApiProblem:
    """Return the problem a malformed or invalid request raises."""
    return ApiProblem(status_code=400, message=message, error_type="bad_request")


def not_found(message: str) -> ApiProblem:
    """Return the problem an unknown resource raises."""
    return ApiProblem(status_code=404, message=message, error_type="not_found")


def conflict(message: str) -> ApiProblem:
    """Return the problem a state conflict raises."""
    return ApiProblem(status_code=409, message=message, error_type="conflict")


#: Persistence errors whose own message is written to be shown, mapped to the
#: status a client acts on.
_PERSISTENCE_STATUS: dict[type[PersistenceError], int] = {
    RecordNotFound: 404,
    DuplicateRecord: 409,
    ConcurrentModification: 409,
    ReferencedRecord: 409,
    BoundExceeded: 400,
    PayloadTooLarge: 413,
}


def _envelope(*, error_type: str, message: str, correlation_id: str) -> dict[str, object]:
    return {"error": {"type": error_type, "message": message, "correlation_id": correlation_id}}


def _status_for(error: PersistenceError) -> int:
    for kind, status in _PERSISTENCE_STATUS.items():
        if isinstance(error, kind):
            return status
    return 500


#: Configuration-service errors whose own message is written to be shown.
_CONFIG_STATUS: dict[type[ConfigServiceError], int] = {
    UnknownNode: 404,
    FieldLocked: 409,
    LockConflict: 409,
    ConfigInvalid: 400,
    ChangeRequiresApproval: 202,
}


def _config_status_for(error: ConfigServiceError) -> int:
    for kind, status in _CONFIG_STATUS.items():
        if isinstance(error, kind):
            return status
    return 400


async def _config_service_error_handler(request: Request, exc: Exception) -> JSONResponse:
    error = cast(ConfigServiceError, exc)
    return JSONResponse(
        status_code=_config_status_for(error),
        content=_envelope(
            error_type=type(error).__name__,
            message=str(error),
            correlation_id=correlation_id_of(request),
        ),
    )


async def _api_problem_handler(request: Request, exc: Exception) -> JSONResponse:
    problem = cast(ApiProblem, exc)
    return JSONResponse(
        status_code=problem.status_code,
        content=_envelope(
            error_type=problem.error_type,
            message=problem.message,
            correlation_id=correlation_id_of(request),
        ),
    )


async def _permission_denied_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content=_envelope(
            error_type="permission_denied",
            message=str(exc),
            correlation_id=correlation_id_of(request),
        ),
    )


async def _token_rejected_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content=_envelope(
            error_type="unauthenticated",
            message=str(exc),
            correlation_id=correlation_id_of(request),
        ),
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _persistence_error_handler(request: Request, exc: Exception) -> JSONResponse:
    error = cast(PersistenceError, exc)
    return JSONResponse(
        status_code=_status_for(error),
        content=_envelope(
            error_type=type(error).__name__,
            message=str(error),
            correlation_id=correlation_id_of(request),
        ),
    )


async def _validation_error_handler(request: Request, _exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=_envelope(
            error_type="validation_error",
            message="The request body did not match the expected shape.",
            correlation_id=correlation_id_of(request),
        ),
    )


async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    error = cast(StarletteHTTPException, exc)
    detail = error.detail if isinstance(error.detail, str) else "request refused"
    return JSONResponse(
        status_code=error.status_code,
        content=_envelope(
            error_type="http_error", message=detail, correlation_id=correlation_id_of(request)
        ),
        headers=error.headers,
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """The last line: an exception nobody classified reaches the client sanitised.

    Full detail — the message, the arguments, whatever a library put in it —
    is logged server-side with the correlation id. The response carries the
    type name and nothing else (FR-004, SC-005).
    """
    correlation_id = correlation_id_of(request)
    logger.error(
        "gateway.unhandled_exception",
        correlation_id=correlation_id,
        path=request.url.path,
        method=request.method,
        detail=_GUARD.render_failure(exc, sink=Sink.CLI),  # local sink: full detail, for the log
    )
    return JSONResponse(
        status_code=500,
        content=_envelope(
            error_type="internal_error",
            message=_GUARD.render_failure(exc, sink=Sink.REST_API),
            correlation_id=correlation_id,
        ),
    )


def install_error_handlers(app: FastAPI) -> None:
    """Register every handler above, so nothing reaches Starlette's own traceback page."""
    app.add_exception_handler(ApiProblem, _api_problem_handler)
    app.add_exception_handler(PermissionDenied, _permission_denied_handler)
    app.add_exception_handler(TokenRejected, _token_rejected_handler)
    app.add_exception_handler(PersistenceError, _persistence_error_handler)
    app.add_exception_handler(ConfigServiceError, _config_service_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)


__all__ = [
    "ApiProblem",
    "bad_request",
    "conflict",
    "install_error_handlers",
    "not_found",
]
