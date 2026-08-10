"""The autonomy routes, and what each one takes to reach.

Nine. The policy half takes the configuration permissions, because a posture
*is* configuration and a deployment that let somebody raise autonomy without
letting them edit the configuration would have two answers to "who decides what
this system may do".

The kill switch takes ``remediation.execute``, which a responder holds. That is
deliberate and it is the one place this table is deliberately permissive: the
control exists for the ten seconds in which an operator has neither the time nor
the confidence to work out what is currently permitted, and a stop that waits
for an administrator is not one.

Reading is separated from writing throughout, so a viewer can see the posture
and what is currently bounding it. An operator who cannot show somebody why
nothing happened is an operator nobody believes.
"""

from __future__ import annotations

from typing import Final

from gateway.http.security.route_permissions import Route
from platform.identity.permissions import Permission

AUTONOMY_ROUTES: Final[tuple[Route, ...]] = (
    Route(
        method="GET",
        path="/v1/autonomy/policy/{node_id}",
        permission=Permission.CONFIG_READ,
    ),
    Route(
        method="PUT",
        path="/v1/autonomy/policy/{node_id}",
        permission=Permission.CONFIG_WRITE,
    ),
    # Previewing writes nothing and still takes the write permission: it is how
    # somebody decides whether to make the change, and it reads the deployment's
    # own decision history to answer. Giving it the read permission would make
    # "what would this do" available to a role that cannot then do it.
    Route(
        method="POST",
        path="/v1/autonomy/policy/{node_id}/preview",
        permission=Permission.CONFIG_WRITE,
    ),
    Route(
        method="POST",
        path="/v1/autonomy/policy/{node_id}/dry-run",
        permission=Permission.CONFIG_WRITE,
    ),
    Route(
        method="POST",
        path="/v1/autonomy/policy/{node_id}/overrides",
        permission=Permission.CONFIG_WRITE,
    ),
    # Explaining is a read: it resolves a hypothetical action and performs
    # nothing. A viewer asking "why did nothing happen" gets an answer.
    Route(
        method="POST",
        path="/v1/autonomy/policy/{node_id}/explain",
        permission=Permission.CONFIG_READ,
    ),
    Route(
        method="GET",
        path="/v1/autonomy/policy/{node_id}/bounds",
        permission=Permission.CONFIG_READ,
    ),
    # Reading it is every viewer's. A screen where nothing is happening looks
    # identical whether nothing needed doing or every automated write is
    # stopped, and only one of those is a thing somebody has to be told. The
    # asymmetry with the two rows below is the point: everybody may know,
    # a responder may decide.
    Route(
        method="GET",
        path="/v1/autonomy/kill-switch",
        permission=Permission.INVESTIGATION_READ,
    ),
    Route(
        method="POST",
        path="/v1/autonomy/kill-switch",
        permission=Permission.REMEDIATION_EXECUTE,
    ),
    Route(
        method="DELETE",
        path="/v1/autonomy/kill-switch",
        permission=Permission.REMEDIATION_EXECUTE,
    ),
)

__all__ = ["AUTONOMY_ROUTES"]
