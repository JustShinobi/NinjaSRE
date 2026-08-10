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
    # --- Pointing the deployment at a source, and looking before it does ------
    # Both take ``estate.manage`` rather than ``estate.read``. The preview
    # stores nothing, which makes it tempting to call a read — but it spends
    # somebody else's provider calls against somebody else's cluster, and a
    # permission that let a viewer do that would be a permission that let a
    # viewer sweep a hypervisor from a browser tab.
    Route(
        method="POST",
        path="/v1/estate/discovery/preview",
        permission=Permission.ESTATE_MANAGE,
    ),
    Route(
        method="POST",
        path="/v1/estate/discovery/sources",
        permission=Permission.ESTATE_MANAGE,
    ),
    # What the last sweep disagreed with the declared inventory about. A read:
    # it answers from what this deployment already stored and reaches nothing.
    Route(method="GET", path="/v1/estate/discovery/report", permission=Permission.ESTATE_READ),
    # Alerts that arrived for something this estate does not hold. The same
    # class of finding as a divergence, and the same permission: it answers from
    # incidents this deployment already stored.
    Route(
        method="GET",
        path="/v1/estate/unresolved-alert-targets",
        permission=Permission.ESTATE_READ,
    ),
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
