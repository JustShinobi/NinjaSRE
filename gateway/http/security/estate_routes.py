"""The estate's routes, and what each one takes to reach.

Five: the listing, the summary, one resource, and the two halves of a
maintenance window. Four read with ``estate.read`` and the maintenance pair
write with ``estate.manage``, which a responder holds — putting a machine into
maintenance while working on it is an incident-time decision, and waiting for an
operator to do it is how the estate stays noisy through every planned change.

Declared here rather than in ``console_routes`` because the estate is not a
console feature: the CLI reads the same paths, and a row in the console's table
would say something untrue about who these are for.
"""

from __future__ import annotations

from typing import Final

from gateway.http.security.route_permissions import Route
from platform.identity.permissions import Permission

ESTATE_ROUTES: Final[tuple[Route, ...]] = (
    Route(method="GET", path="/v1/estate/resources", permission=Permission.ESTATE_READ),
    Route(method="GET", path="/v1/estate/summary", permission=Permission.ESTATE_READ),
    Route(
        method="GET",
        path="/v1/estate/resources/{resource_id}",
        permission=Permission.ESTATE_READ,
    ),
    Route(
        method="POST",
        path="/v1/estate/resources/{resource_id}/maintenance",
        permission=Permission.ESTATE_MANAGE,
    ),
    Route(
        method="DELETE",
        path="/v1/estate/resources/{resource_id}/maintenance",
        permission=Permission.ESTATE_MANAGE,
    ),
)

__all__ = ["ESTATE_ROUTES"]
