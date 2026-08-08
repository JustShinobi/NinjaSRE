"""The closed-loop routes, and what each one takes to reach.

Six: four reads and two writes. The reads take ``incident.read``, which a viewer
holds — a deployment that changed production and will not say whether it worked
is talking to itself. The writes take ``remediation.execute``, which is stronger
than the responder permission the incident writes take, and deliberately so:
clearing a suspension is authorising the deployment to act unattended on a
resource whose state nobody is sure of, and closing a recurring problem is
authorising it to start repeating something it had been stopped from repeating.
Both are decisions about *autonomy* rather than about an incident.

Declared here rather than in ``console_routes`` for the reason the incident
rows are: the CLI reads the same paths, and a row in the console's table would
say something untrue about who they are for.
"""

from __future__ import annotations

from typing import Final

from gateway.http.security.route_permissions import Route
from platform.identity.permissions import Permission

REMEDIATION_ROUTES: Final[tuple[Route, ...]] = (
    Route(method="GET", path="/v1/remediations", permission=Permission.INCIDENT_READ),
    Route(
        method="GET",
        path="/v1/remediations/effectiveness/summary",
        permission=Permission.INCIDENT_READ,
    ),
    Route(
        method="GET",
        path="/v1/remediations/problems/recurring",
        permission=Permission.INCIDENT_READ,
    ),
    Route(
        method="GET",
        path="/v1/remediations/suspensions",
        permission=Permission.INCIDENT_READ,
    ),
    Route(
        method="GET",
        path="/v1/remediations/{action_id}",
        permission=Permission.INCIDENT_READ,
    ),
    # Both writes are about autonomy rather than about an incident, which is why
    # neither takes ``incident.manage``.
    Route(
        method="POST",
        path="/v1/remediations/problems/{problem_id}/close",
        permission=Permission.REMEDIATION_EXECUTE,
    ),
    Route(
        method="POST",
        path="/v1/remediations/suspensions/{resource_id}/clear",
        permission=Permission.REMEDIATION_EXECUTE,
    ),
)

__all__ = ["REMEDIATION_ROUTES"]
