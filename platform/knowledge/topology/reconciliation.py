"""The three-way merge: discovered, stored, and what an operator wrote.

Re-running discovery is the operation this whole package has to survive, and the
naive version of it — replace what the source covers — is wrong in two ways that
cost different things.

It **destroys operator annotations**, which are the only part of a topology that
records what no scraper could have observed: that a dependency is used during
failover, that a queue is drained by hand on Fridays, that a service is being
retired. A team whose annotations disappear on the next discovery run stops
writing them, and the graph decays to whatever the adapters can see.

It **deletes a team's topology when an API has a bad minute**. A partially failed
Kubernetes read reports a third of the estate, and "replace" reads the missing
two thirds as retired. The blast radius is wrong on the next incident and nobody
knows why.

So the merge has six cases, and the table below is the whole feature:

===========================================  ==================================
Situation                                    Action
===========================================  ==================================
Discovered, not stored                       Add, stamped and verified
Discovered and stored                        Refresh the stamp, keep annotations
Stored, not discovered, source healthy       Remove
Stored, not discovered, source degraded      **Mark unverified. Do not remove.**
Operator-authored, anything                  Never removed, never overwritten
Annotated, anything                          Annotations always preserved
===========================================  ==================================

The fourth row is the one that matters, and it is why ``DiscoveryHealth`` has
three members rather than two.

Removal is scoped to what the source says it ``covered``. A Kubernetes adapter
watching one namespace must not remove the dependencies of a service in another
namespace it was never looking at — and a source that names nothing it inspected
removes nothing, whatever its health.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

from platform.knowledge.clock import now as _utc_now
from platform.knowledge.topology.discovery.port import (
    DiscoveredTopology,
    DiscoveryHealth,
    DiscoverySource,
)
from platform.knowledge.topology.models import DependencyEdge, ServiceNode
from platform.knowledge.topology.queries import dependency_edges
from platform.knowledge.topology.write import TopologyWriter
from platform.observability.logging import get_logger
from platform.persistence.errors import TopologyUnavailable
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope

logger = get_logger(__name__)

#: An edge as the audit record names it. Readable in a log line, and stable
#: enough to grep for when somebody asks what happened to a dependency.
EDGE_LABEL = "{from_node_id}->{to_node_id} ({kind})"


def label(key: tuple[str, str, str]) -> str:
    """Return the readable form of an edge key, for an audit record."""
    from_node_id, to_node_id, kind = key
    return EDGE_LABEL.format(from_node_id=from_node_id, to_node_id=to_node_id, kind=kind)


@dataclass(frozen=True, slots=True)
class Reconciliation:
    """The diff one discovery run applied, kept for audit (FR-007).

    Every list is edge keys rather than edges. An audit record is read by a
    human asking "what changed", and a hundred serialised property bags is not an
    answer to that question.
    """

    source: str
    health: DiscoveryHealth
    at: datetime
    applied: bool = True
    added: tuple[tuple[str, str, str], ...] = ()
    refreshed: tuple[tuple[str, str, str], ...] = ()
    removed: tuple[tuple[str, str, str], ...] = ()
    unverified: tuple[tuple[str, str, str], ...] = ()
    annotations_preserved: tuple[tuple[str, str, str], ...] = ()
    services: int = 0
    reason: str = ""

    @property
    def changed(self) -> bool:
        """Return whether this run altered the graph at all."""
        return bool(self.added or self.removed or self.unverified)

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable audit record of this run."""
        return {
            "source": self.source,
            "health": self.health.value,
            "at": self.at.isoformat(),
            "applied": self.applied,
            "added": [label(key) for key in self.added],
            "refreshed": [label(key) for key in self.refreshed],
            "removed": [label(key) for key in self.removed],
            "unverified": [label(key) for key in self.unverified],
            "annotations_preserved": [label(key) for key in self.annotations_preserved],
            "services": self.services,
            "reason": self.reason,
        }


@dataclass(slots=True)
class TopologyReconciler:
    """Applies a discovery run to one team's graph, without losing what is there."""

    gateway: PersistenceGateway
    scope: TenantScope
    clock: Callable[[], datetime] = _utc_now
    writer: TopologyWriter = field(init=False)

    def __post_init__(self) -> None:
        self.writer = TopologyWriter(gateway=self.gateway, scope=self.scope, clock=self.clock)

    async def run(self, source: DiscoverySource) -> Reconciliation:
        """Ask ``source`` what it can see and apply the result."""
        return await self.apply(await source.discover())

    async def apply(self, discovered: DiscoveredTopology) -> Reconciliation:
        """Apply one discovery run and return the diff it produced.

        A failed run applies nothing at all — not even an unverified mark. A
        source that could not run has observed no fact about the estate, and
        marking everything it covers as unverified on the strength of one flaky
        adapter would make the label meaningless within a week.
        """
        moment = self.clock()
        if not discovered.health.observed:
            logger.info(
                "topology.discovery_failed",
                source=discovered.source,
                reason=discovered.reason,
            )
            return Reconciliation(
                source=discovered.source,
                health=discovered.health,
                at=moment,
                applied=False,
                reason=discovered.reason,
            )

        try:
            report = await self._apply(discovered, moment)
        except TopologyUnavailable as unavailable:
            logger.warning("topology.reconcile_unavailable", reason=str(unavailable))
            return Reconciliation(
                source=discovered.source,
                health=discovered.health,
                at=moment,
                applied=False,
                reason=str(unavailable),
            )

        logger.info("topology.reconciled", **report.to_record())
        return report

    async def _apply(self, discovered: DiscoveredTopology, moment: datetime) -> Reconciliation:
        """Do the merge, inside one unit of work.

        One transaction for the whole run, so a reconciliation that fails halfway
        leaves the graph as it was rather than half-updated. A half-applied
        discovery is the state that produces a wrong blast radius nobody can
        explain afterwards.
        """
        discovered_edges = discovered.edges_by_key()
        added: list[tuple[str, str, str]] = []
        refreshed: list[tuple[str, str, str]] = []
        removed: list[tuple[str, str, str]] = []
        unverified: list[tuple[str, str, str]] = []
        preserved: list[tuple[str, str, str]] = []

        async with self.gateway.begin(self.scope) as uow:
            for service in _stamped_services(discovered.nodes, moment, discovered.source):
                await self.writer.write_service(uow, service)

            stored: dict[tuple[str, str, str], DependencyEdge] = {}
            for node_id in discovered.covered:
                for edge in dependency_edges(await uow.topology.edges_from(node_id)):
                    stored[edge.key] = edge

            for key, edge in discovered_edges.items():
                previous = stored.get(key)
                verified = edge.verified(moment, source=discovered.source)
                if previous is None:
                    added.append(key)
                else:
                    refreshed.append(key)
                    if previous.annotations:
                        preserved.append(key)
                await self.writer.write_dependency(uow, verified)

            for key, edge in sorted(stored.items()):
                if key in discovered_edges or edge.operator_authored:
                    continue
                if discovered.health.complete:
                    await uow.topology.delete_edge(edge.to_stored())
                    removed.append(key)
                    continue
                # Degraded: the source did not see this edge and cannot say
                # whether it is gone. Mark it and keep the timestamp of the last
                # run that did see it — when it was last confirmed is what a
                # reader needs to weigh it (FR-008).
                await uow.topology.upsert_edge(edge.marked_unverified().to_stored())
                unverified.append(key)

        return Reconciliation(
            source=discovered.source,
            health=discovered.health,
            at=moment,
            added=tuple(added),
            refreshed=tuple(refreshed),
            removed=tuple(removed),
            unverified=tuple(unverified),
            annotations_preserved=tuple(preserved),
            services=len(discovered.nodes),
            reason=discovered.reason,
        )


def _stamped_services(
    services: Sequence[ServiceNode], moment: datetime, source: str
) -> tuple[ServiceNode, ...]:
    """Return ``services`` stamped as seen by ``source`` at ``moment``.

    Annotations are deliberately not touched. The store merges properties, and
    the annotations a discovery source carries are whatever the estate declared —
    which is merged over the operator's rather than replacing them, because
    ``upsert_node`` merges and the operator's write happened first.
    """
    return tuple(
        replace(service, verified_at=moment, unverified=False, source=source)
        for service in services
    )


__all__ = [
    "EDGE_LABEL",
    "Reconciliation",
    "TopologyReconciler",
    "label",
]
