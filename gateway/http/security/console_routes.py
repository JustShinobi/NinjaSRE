"""The routes a human-facing client needs, and what each one takes to reach.

Feature 014 declared ``/auth``, ``/identity``, and ``/audit`` before anything
served them; those rows already exist in ``route_permissions.ROUTE_TABLE`` and
are not repeated here. What this adds is the ``/v1`` half — the reads a console
makes that the API did not yet answer — plus nothing else, because a row here
that duplicated one there would be refused at composition and rightly so.

The permission on each row is the one the *data* needs, never the one the screen
implies. A capability catalogue is read with ``investigation.read`` because it
describes what a run could do; the configuration it is resolved against is read
with ``config.read``, and the catalogue route needs both — so it takes the
narrower of the two, which is ``config.read``.
"""

from __future__ import annotations

from typing import Final

from gateway.http.security.route_permissions import Route
from platform.identity.permissions import Permission

CONSOLE_ROUTES: Final[tuple[Route, ...]] = (
    # --- The organisation tree and what a change to it would do ---------------
    Route(method="GET", path="/v1/config", permission=Permission.CONFIG_READ),
    # A preview computes; it never stores. Read is therefore the honest
    # permission: an operator who may not write should still be able to see what
    # a proposal would do before asking somebody who may.
    Route(method="POST", path="/v1/config/{node_id}/preview", permission=Permission.CONFIG_READ),
    Route(method="GET", path="/v1/config/{node_id}/catalogue", permission=Permission.CONFIG_READ),
    # The editable fields and where each value comes from. ``config.read``
    # rather than ``config.write``: it describes the shape of the document and
    # what applies, which is exactly what somebody who may only read is entitled
    # to see. What may be *changed* is decided at the write.
    Route(method="GET", path="/v1/config/{node_id}/fields", permission=Permission.CONFIG_READ),
    # The shipped detector set as this node runs it, resolved server-side. Read
    # with ``config.read`` because what varies between deployments is entirely
    # configuration — the topology that was detected and the overrides applied
    # to it. The catalogue itself is the same in every copy of the release.
    Route(method="GET", path="/v1/config/{node_id}/guardian", permission=Permission.CONFIG_READ),
    Route(
        method="GET",
        path="/v1/config/{node_id}/integration-schemas",
        permission=Permission.CONFIG_READ,
    ),
    # The facts a team has added to the agent's prompt, the exact text the model
    # will receive, and — for a node that has written none — the starting
    # document derived from what the estate has already discovered. ``config.read``
    # for the same reason ``fields`` is: it describes what applies, and nothing
    # here stores anything.
    Route(
        method="GET",
        path="/v1/config/{node_id}/operating-context",
        permission=Permission.CONFIG_READ,
    ),
    # A preview computes and never stores, so it takes read for the same reason
    # the configuration preview does: somebody who may not write should still be
    # able to see what a proposal would send to the model before asking somebody
    # who may.
    Route(
        method="POST",
        path="/v1/config/{node_id}/operating-context/preview",
        permission=Permission.CONFIG_READ,
    ),
    # --- Approvals, and the rollback that follows one -------------------------
    Route(method="GET", path="/v1/approvals", permission=Permission.APPROVAL_READ),
    Route(method="GET", path="/v1/approvals/{approval_id}", permission=Permission.APPROVAL_READ),
    Route(
        method="POST",
        path="/v1/approvals/{approval_id}/rollback",
        permission=Permission.REMEDIATION_EXECUTE,
    ),
    # --- What the agent has proposed, and the deciding of it -------------------
    # Read with ``approval.read`` because a proposal *is* an approval request:
    # the queue is the same store and the same right to see what is waiting.
    # Deciding takes ``approval.review``, which is the narrower right, and it is
    # the one that matters — an approved proposal writes configuration, and
    # ``config.write`` is not asked for because the write is the platform's own
    # rather than the reviewer's. What a reviewer is being trusted with is the
    # decision.
    Route(method="GET", path="/v1/proposals", permission=Permission.APPROVAL_READ),
    Route(method="GET", path="/v1/proposals/count", permission=Permission.APPROVAL_READ),
    Route(method="GET", path="/v1/proposals/{proposal_id}", permission=Permission.APPROVAL_READ),
    Route(
        method="POST",
        path="/v1/proposals/{proposal_id}/decision",
        permission=Permission.APPROVAL_REVIEW,
    ),
    # --- Learned material ------------------------------------------------------
    Route(method="GET", path="/v1/topology/{node_id}", permission=Permission.MEMORY_READ),
    Route(method="GET", path="/v1/knowledge/documents", permission=Permission.KNOWLEDGE_READ),
    Route(
        method="GET",
        path="/v1/knowledge/documents/{document_id}",
        permission=Permission.KNOWLEDGE_READ,
    ),
)

__all__ = ["CONSOLE_ROUTES"]
