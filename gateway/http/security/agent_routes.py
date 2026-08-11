"""The agent's own description, and what it takes to reach it.

One row. The pipeline declaration is what the software *is* rather than what a
deployment configured, so it takes ``investigation.read`` — the same permission
the capability catalogue takes, and for the same reason: somebody who may read
an investigation is entitled to know what produced it.
"""

from __future__ import annotations

from typing import Final

from gateway.http.security.route_permissions import Route
from platform.identity.permissions import Permission

AGENT_ROUTES: Final[tuple[Route, ...]] = (
    Route(method="GET", path="/v1/agent/pipeline", permission=Permission.INVESTIGATION_READ),
)

__all__ = ["AGENT_ROUTES"]
