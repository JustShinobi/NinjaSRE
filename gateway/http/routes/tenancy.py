"""Filtering a run to the caller's own team (FR-003, SC-006).

``AgentRun`` is scoped to an organisation by the persistence layer, not to a
team — a run's team is a value inside ``metadata``, because the same store
serves every team in an organisation and team is a fact about who started the
run, not about where it lives. That means team isolation is this surface's
job: every read of a run, its turns, its evidence, or its interactions checks
the metadata against the caller's own team before returning anything, and an
org-wide token — one with no team of its own — sees every team's runs, which
is what "org-wide" is supposed to mean.
"""

from __future__ import annotations

from collections.abc import Sequence

from config.constants.runs import RUN_METADATA_TEAM
from gateway.http.deps import AuthenticatedRequest
from platform.persistence.ports.config_repository import ConfigNode
from platform.persistence.ports.run_trace_store import AgentRun


def visible(run: AgentRun, auth: AuthenticatedRequest) -> bool:
    """Return whether ``run`` is within the caller's own team, or the caller is org-wide."""
    if not auth.team_node_id:
        return True
    return str(run.metadata.get(RUN_METADATA_TEAM, "")) == auth.team_node_id


def within_scope(node_id: str, auth: AuthenticatedRequest, ancestors: Sequence[ConfigNode]) -> bool:
    """Return whether ``node_id`` is the caller's own team or beneath it.

    The permission guard alone cannot tell: a team-scoped token's own node
    always wins over whatever the path names
    (``platform/identity/authorisation.py``), so a route addressing an
    arbitrary node by path parameter — ``/v1/config/{node_id}`` — has to check
    this itself, or a team holding a permission at its own node could read or
    write any node in the organisation just by naming it (SC-006). ``ancestors``
    is ``node_id``'s own root-first chain, inclusive.
    """
    if not auth.team_node_id:
        return True
    chain = {ancestor.node_id for ancestor in ancestors}
    return node_id in chain and auth.team_node_id in chain


__all__ = ["visible", "within_scope"]
