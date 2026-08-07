"""One identifier per request, carried into the run trace (FR-008).

A client that supplies ``X-Correlation-Id`` gets it back unchanged, so a caller
that already has an identifier for the request — a queueing system, a webhook
source's own event id — can thread it straight through rather than reconciling
two. A client that supplies nothing gets one minted here, because "no
correlation id" is not a state any request should be in by the time it reaches
a handler.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

#: The header a client may supply, and the one every response carries.
CORRELATION_ID_HEADER = "X-Correlation-Id"


def new_correlation_id() -> str:
    """Return a fresh correlation identifier."""
    return uuid.uuid4().hex


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attaches a correlation id to every request and echoes it on the response."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        correlation_id = (
            request.headers.get(CORRELATION_ID_HEADER, "").strip() or new_correlation_id()
        )
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers[CORRELATION_ID_HEADER] = correlation_id
        return response


def correlation_id_of(request: Request) -> str:
    """Return the correlation id ``CorrelationIdMiddleware`` attached to ``request``."""
    return str(getattr(request.state, "correlation_id", "") or new_correlation_id())


__all__ = [
    "CORRELATION_ID_HEADER",
    "CorrelationIdMiddleware",
    "correlation_id_of",
    "new_correlation_id",
]
