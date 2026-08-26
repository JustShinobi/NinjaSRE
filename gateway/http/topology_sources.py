"""Composing the graph one investigation traverses, per run and per team.

The capability was shipped, discovered, ranked and offered, and nothing in this
deployment ever bound it a source — so every call returned the same sentence,
that the graph is not configured. That is the honest answer to "nobody composed
one" and a useless one to receive on every investigation.

**Per run rather than at boot**, which is why this is a factory handed to the
runner rather than a ``bind`` at startup like the log source. A log system is a
deployment-wide address; a graph is read under a *tenant scope*, and a scope
composed once at boot is one organisation's scope answering every organisation's
runs. The runner binds what this builds for the length of one investigation and
puts back whatever it displaced, so what a run traverses is its own.

**Bind only what can answer**, which is the same posture the log source takes and
for the same reason: the tool's unbound path says the graph is not configured,
and the catalogue leaves an unbound capability out of the run entirely. Both are
better than offering a traversal that will refuse — a capability offered is a
tool slot and, when the model reaches for it, a turn.

So two things are checked before anything is bound, and they are checked
separately because they are two different facts about a deployment.

**The team's own switch.** ``policies.knowledge.topology_enabled`` is resolved
from the configuration tree for the team this run belongs to, and a team that
switched topology off gets the unbound behaviour rather than an empty answer. An
ablation that left the capability offered and refusing would still perturb the
catalogue it was supposed to remove itself from.

**Whether the graph can be reached at all.** ``available`` never raises, and a
deployment without the Apache AGE extension is one where there is nowhere to
look.

What is *not* here is a check on whether the graph holds anything. An empty
graph answers, and "nothing is recorded about checkout" is a finding an
investigation continues past. Refusing to bind over an empty graph would collapse
that back into the unavailability this module exists to stop being the only
answer.
"""

from __future__ import annotations

from capabilities.tools.system.topology_query.binding import TopologySource
from gateway.http.services import InvestigationStart
from gateway.http.state import GatewayState
from platform.config_service.bindings import knowledge_policy
from platform.config_service.service import ConfigService
from platform.knowledge.topology.queries import TopologyQueries
from platform.observability.logging import get_logger
from platform.persistence.ports.transaction import TenantScope

logger = get_logger(__name__)


async def topology_source_for(
    state: GatewayState, request: InvestigationStart, *, org_id: str = ""
) -> TopologySource | None:
    """Return the graph path ``request``'s run may traverse, or ``None`` for none.

    ``org_id`` is the deployment's own organisation, used when the run does not
    name one. A run that names neither gets nothing: inventing a scope here is
    how a traversal ends up in another tenant's subgraph, and the capability's
    own binding module refuses a fallback for exactly that reason.
    """
    organisation = request.org_id or org_id
    if not organisation:
        logger.info("topology.source_skipped", run_id=request.run_id, reason="unscoped run")
        return None

    scope = TenantScope(org_id=organisation, team_node_id=request.team_node_id or None)
    node_id = request.team_node_id or organisation
    try:
        effective = await ConfigService(gateway=state.gateway, scope=scope).resolve(node_id)
    except Exception as unreadable:  # noqa: BLE001 — an optional source must not fail a run
        logger.warning("topology.policy_unreadable", run_id=request.run_id, error=str(unreadable))
        return None

    policy = knowledge_policy(effective.config.policies)
    if not policy.topology_enabled:
        logger.info("topology.source_disabled", run_id=request.run_id, team=node_id)
        return None

    queries = TopologyQueries(gateway=state.gateway, scope=scope, policy=policy)
    available, reason = await queries.available()
    if not available:
        logger.info("topology.source_unavailable", run_id=request.run_id, reason=reason)
        return None

    logger.info("topology.source_composed", run_id=request.run_id, team=node_id)
    return queries


def compose_topology_sources(state: GatewayState, *, org_id: str) -> None:
    """Give the runner what to build each investigation's graph path with.

    Through ``attach_sources`` rather than by binding here, because the binding
    belongs to a run and this is called once. A runner that does not take the
    seam — a stand-in in a deployment that composed no investigation runtime — is
    a state rather than an error, and is logged as one.
    """
    attach = getattr(state.investigator, "attach_sources", None)
    if attach is None:
        logger.info("topology.sources_skipped", reason="no investigation runner is composed")
        return

    async def build(request: InvestigationStart) -> TopologySource | None:
        """Return this run's own graph path."""
        return await topology_source_for(state, request, org_id=org_id)

    attach(topology=build)
    logger.info("topology.sources_composed", org_id=org_id)


__all__ = ["compose_topology_sources", "topology_source_for"]
