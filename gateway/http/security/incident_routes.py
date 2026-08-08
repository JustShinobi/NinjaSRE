"""The incident and detector routes, and what each one takes to reach.

Nine: four reads and five writes. The reads take ``incident.read``, which a
viewer holds — an incident list nobody may look at is a deployment talking to
itself. The writes take ``incident.manage``, which a responder holds, for the
reason ``estate.manage`` is theirs: deciding an incident is noise is an
incident-time judgement, and a list of open incidents that only an operator may
close is a list that stops being read.

Declared here rather than in ``console_routes`` because these are not a console
feature: the CLI reads the same paths, and a row in the console's table would
say something untrue about who they are for.
"""

from __future__ import annotations

from typing import Final

from gateway.http.security.route_permissions import Route
from platform.identity.permissions import Permission

INCIDENT_ROUTES: Final[tuple[Route, ...]] = (
    Route(method="GET", path="/v1/incidents", permission=Permission.INCIDENT_READ),
    Route(
        method="GET",
        path="/v1/incidents/{incident_id}",
        permission=Permission.INCIDENT_READ,
    ),
    Route(
        method="POST",
        path="/v1/incidents/{incident_id}/close",
        permission=Permission.INCIDENT_MANAGE,
    ),
    Route(
        method="POST",
        path="/v1/incidents/{incident_id}/suppress",
        permission=Permission.INCIDENT_MANAGE,
    ),
    Route(method="GET", path="/v1/detectors", permission=Permission.INCIDENT_READ),
    Route(method="GET", path="/v1/observations", permission=Permission.INCIDENT_READ),
    # A dry run writes nothing and fires nothing, and still takes the write
    # permission: it is how somebody decides whether to change a threshold, and
    # it is answered from the team's own signals.
    Route(
        method="POST",
        path="/v1/detectors/{detector_id}/dry-run",
        permission=Permission.INCIDENT_MANAGE,
    ),
    Route(
        method="POST",
        path="/v1/detectors/{detector_id}/enable",
        permission=Permission.INCIDENT_MANAGE,
    ),
    Route(
        method="POST",
        path="/v1/detectors/{detector_id}/disable",
        permission=Permission.INCIDENT_MANAGE,
    ),
)

__all__ = ["INCIDENT_ROUTES"]
