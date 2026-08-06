"""Reading the graph: bounded, cycle-safe, team-scoped, and honest when it cannot.

A thin layer over the storage catalogue, and the three things it adds are each a
requirement rather than a convenience.

**Transitive dependencies are assembled here.** The catalogue offers transitive
*dependents* — that is blast radius, and storage computes it — but only one hop
of dependencies. Walking further is this module's job, and it is where the cycle
matters: ``checkout -> payments -> checkout`` is a legal topology, and a walk
without a visited set does not return. The origin is excluded from its own
dependency set for the same reason it would be useless to include it.

**Every answer says how it was bounded.** Depth is capped by ``MAX_GRAPH_DEPTH``
and a request above it raises rather than being clamped — a blast radius silently
computed at depth 5 when the caller asked for 40 looks complete and is not.
Result size is capped by ``MAX_GRAPH_RESULTS`` and *is* cut, but ``truncated``
travels on the answer so a partial impact statement is never read as a complete
one.

**Unavailability is not emptiness.** "Nothing depends on this service" and "we
cannot currently tell you what depends on this service" lead to opposite
decisions, and the second is not a finding about the service. A graph that cannot
answer produces an answer with ``searched=False`` and a reason, the run continues,
and the degradation is in the trace where an operator can see it (FR-009).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from config.constants.persistence import (
    DEFAULT_GRAPH_DEPTH,
    MAX_GRAPH_DEPTH,
    MAX_GRAPH_RESULTS,
)
from config.prompts.knowledge import TOPOLOGY_DISABLED
from platform.knowledge.clock import now as _utc_now
from platform.knowledge.policy import KnowledgePolicy
from platform.knowledge.topology.models import (
    BlastRadius,
    DependencyEdge,
    DependencySet,
    ReachedService,
    ServiceNode,
)
from platform.observability.logging import get_logger
from platform.persistence.errors import BoundExceeded, PersistenceError, TopologyUnavailable
from platform.persistence.ports.topology_graph import TopologyEdge
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope, UnitOfWork

logger = get_logger(__name__)


def check_depth(depth: int) -> int:
    """Return ``depth``, or raise if it is outside the traversal bound (FR-004).

    Raised rather than clamped, and checked here as well as in storage: this
    module walks dependencies itself, so a depth that never reaches a repository
    would otherwise be unbounded exactly where the walk is.
    """
    if depth > MAX_GRAPH_DEPTH:
        raise BoundExceeded(
            parameter="depth",
            requested=depth,
            limit=MAX_GRAPH_DEPTH,
            constant="MAX_GRAPH_DEPTH",
        )
    if depth < 1:
        raise ValueError(f"A traversal must cross at least one hop, got {depth}.")
    return depth


@dataclass(frozen=True, slots=True)
class ServiceTopology:
    """Everything one topology question returns, in both directions.

    One record rather than three calls, because the agent's question is "what
    should I know about this service" and answering it in three round trips is
    three chances to get two of them and reason from half a picture.
    """

    service: str
    depth: int
    dependencies: DependencySet
    dependents: DependencySet
    blast_radius: BlastRadius
    searched: bool = True
    reason: str = ""

    @property
    def empty(self) -> bool:
        """Return whether the graph held nothing at all for this service."""
        return self.dependencies.empty and self.dependents.empty and self.blast_radius.empty

    @property
    def truncated(self) -> bool:
        """Return whether any of the three traversals hit the result bound."""
        return (
            self.dependencies.truncated or self.dependents.truncated or self.blast_radius.truncated
        )

    def stale_services(self, moment: datetime) -> tuple[ServiceNode, ...]:
        """Return the services in this answer nothing has verified recently."""
        seen: dict[str, ServiceNode] = {}
        for service in (*self.dependencies.services, *self.dependents.services):
            if service.stale_at(moment):
                seen.setdefault(service.node_id, service)
        return tuple(seen.values())


@dataclass(slots=True)
class TopologyRecord:
    """One topology query as the run trace records it (FR-023)."""

    service: str
    depth: int
    dependencies: tuple[str, ...] = ()
    dependents: tuple[str, ...] = ()
    blast_radius: int = 0
    truncated: bool = False
    searched: bool = True
    reason: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this query."""
        return {
            "service": self.service,
            "depth": self.depth,
            "dependencies": list(self.dependencies),
            "dependents": list(self.dependents),
            "blast_radius": self.blast_radius,
            "truncated": self.truncated,
            "searched": self.searched,
            "reason": self.reason,
        }


@dataclass(slots=True)
class TopologyLedger:
    """Every topology query one run made, and what came back.

    Run-scoped and mutable, handed to the queries object at construction. The
    ablation this feature has to answer for is whether topology changed the
    investigation, and a run where the graph was queried three times and returned
    nothing every time is a different observation from one where it was never
    queried at all.
    """

    records: list[TopologyRecord] = field(default_factory=list)

    def record(self, answer: ServiceTopology) -> TopologyRecord:
        """Store ``answer`` and return the record it produced."""
        entry = TopologyRecord(
            service=answer.service,
            depth=answer.depth,
            dependencies=answer.dependencies.names(),
            dependents=answer.dependents.names(),
            blast_radius=len(answer.blast_radius.reaches),
            truncated=answer.truncated,
            searched=answer.searched,
            reason=answer.reason,
        )
        self.records.append(entry)
        return entry

    def trace_summary(self) -> dict[str, Any]:
        """Return what the run trace records about topology use."""
        return {
            "topology_queries": len(self.records),
            "topology_queries_with_results": sum(
                1 for entry in self.records if entry.dependencies or entry.dependents
            ),
            "topology_degradations": sum(1 for entry in self.records if not entry.searched),
            "topology_records": [entry.to_record() for entry in self.records],
        }


@dataclass(slots=True)
class TopologyQueries:
    """The team's view of the graph, bounded and recorded."""

    gateway: PersistenceGateway
    scope: TenantScope
    policy: KnowledgePolicy = field(default_factory=KnowledgePolicy)
    ledger: TopologyLedger = field(default_factory=TopologyLedger)
    clock: Callable[[], datetime] = _utc_now

    # -- the composite ---------------------------------------------------------

    async def query(
        self,
        service: str,
        *,
        depth: int = DEFAULT_GRAPH_DEPTH,
        record: bool = True,
    ) -> ServiceTopology:
        """Return what the graph knows about ``service``, or why it does not.

        Three outcomes, and they are three because the next move differs for
        each. A populated answer narrows the investigation. An empty answer is a
        gap in the topology data and the investigation continues unchanged. An
        unavailability means there was nowhere to look — returning it as an empty
        answer would teach the agent that a service has no dependents when the
        truth is that nobody installed the graph extension.
        """
        bounded = check_depth(depth)
        if not self.policy.topology_enabled:
            return self._recorded(_degraded(service, bounded, TOPOLOGY_DISABLED), record=record)

        try:
            async with self.gateway.begin(self.scope) as uow:
                dependencies = await self._dependencies(uow, service, depth=bounded)
                dependents = await self._dependents(uow, service)
                radius = await self._blast_radius(uow, service, depth=bounded)
        except TopologyUnavailable as unavailable:
            logger.info("topology.unavailable", service=service, reason=str(unavailable))
            return self._recorded(_degraded(service, bounded, str(unavailable)), record=record)
        except PersistenceError as error:
            logger.warning("topology.query_failed", service=service, error=str(error))
            return self._recorded(_degraded(service, bounded, str(error)), record=record)

        answer = ServiceTopology(
            service=service,
            depth=bounded,
            dependencies=dependencies,
            dependents=dependents,
            blast_radius=radius,
        )
        logger.info(
            "topology.queried",
            service=service,
            depth=bounded,
            dependencies=len(dependencies.services),
            dependents=len(dependents.services),
            blast_radius=len(radius.reaches),
            truncated=answer.truncated,
        )
        return self._recorded(answer, record=record)

    # -- the individual traversals ---------------------------------------------

    async def dependencies(
        self, service: str, *, depth: int = DEFAULT_GRAPH_DEPTH
    ) -> DependencySet:
        """Return what ``service`` depends on, out to ``depth`` hops."""
        bounded = check_depth(depth)
        async with self.gateway.begin(self.scope) as uow:
            return await self._dependencies(uow, service, depth=bounded)

    async def dependents(self, service: str) -> DependencySet:
        """Return what depends on ``service``, one hop in."""
        async with self.gateway.begin(self.scope) as uow:
            return await self._dependents(uow, service)

    async def blast_radius(self, service: str, *, depth: int = DEFAULT_GRAPH_DEPTH) -> BlastRadius:
        """Return what an outage at ``service`` would reach, nearest first."""
        bounded = check_depth(depth)
        async with self.gateway.begin(self.scope) as uow:
            return await self._blast_radius(uow, service, depth=bounded)

    async def path(self, from_service: str, to_service: str) -> tuple[ServiceNode, ...]:
        """Return the shortest dependency path between two services, or ``()``."""
        async with self.gateway.begin(self.scope) as uow:
            found = await uow.topology.shortest_path(from_service, to_service)
        return tuple(ServiceNode.from_stored(node) for node in found)

    async def dependency_edges(self, service: str) -> tuple[DependencyEdge, ...]:
        """Return the stored edges leaving ``service``, with their annotations.

        The only read that returns edges rather than services. Reconciliation and
        the operator surfaces need it; the agent-facing answer does not, because
        an annotation is written for a human and a traversal is answered for a
        model.
        """
        async with self.gateway.begin(self.scope) as uow:
            return dependency_edges(await uow.topology.edges_from(service))

    async def available(self) -> tuple[bool, str]:
        """Return whether the graph can answer, and why not when it cannot.

        Never raises. This is the method a caller uses to find out whether the
        others will, so it has to answer even when nothing else can.
        """
        if not self.policy.topology_enabled:
            return False, TOPOLOGY_DISABLED
        try:
            async with self.gateway.begin(self.scope) as uow:
                status = await uow.topology.availability()
        except PersistenceError as error:
            return False, str(error)
        return status.available, status.reason or ""

    # -- internals -------------------------------------------------------------

    async def _dependencies(self, uow: UnitOfWork, service: str, *, depth: int) -> DependencySet:
        """Return a cycle-safe, bounded walk outward from ``service`` (FR-005).

        Breadth-first, so the bound cuts the frontier rather than a branch: the
        services one hop out are the ones an investigation checks first, and a
        depth-first walk that spent the whole result budget on one long chain
        would leave them out.
        """
        seen = {service}
        frontier = [service]
        found: dict[str, ServiceNode] = {}
        truncated = False

        for _ in range(depth):
            if not frontier or truncated:
                break
            next_frontier: list[str] = []
            for current in frontier:
                result = await uow.topology.direct_dependencies(current)
                truncated = truncated or result.truncated
                for stored in result.nodes:
                    if stored.node_id in seen:
                        continue
                    seen.add(stored.node_id)
                    if len(found) >= MAX_GRAPH_RESULTS:
                        truncated = True
                        break
                    found[stored.node_id] = ServiceNode.from_stored(stored)
                    next_frontier.append(stored.node_id)
                if truncated:
                    break
            frontier = next_frontier

        return DependencySet(
            origin=service,
            services=tuple(found.values()),
            truncated=truncated,
            depth=depth,
        )

    async def _dependents(self, uow: UnitOfWork, service: str) -> DependencySet:
        """Return the one-hop dependents of ``service``.

        One hop, deliberately. The transitive version is ``blast_radius``, which
        carries the distances — and a dependent set without distances is the
        thing an operator would mistake for "who to page".
        """
        result = await uow.topology.direct_dependents(service)
        return DependencySet(
            origin=service,
            services=tuple(ServiceNode.from_stored(node) for node in result.nodes),
            truncated=result.truncated,
        )

    async def _blast_radius(self, uow: UnitOfWork, service: str, *, depth: int) -> BlastRadius:
        """Return the stored blast radius as the domain record."""
        stored = await uow.topology.blast_radius(service, depth=depth)
        return BlastRadius(
            origin=service,
            max_depth=depth,
            reaches=tuple(
                ReachedService(service=ServiceNode.from_stored(entry.node), depth=entry.depth)
                for entry in stored.reaches
            ),
            truncated=stored.truncated,
        )

    def _recorded(self, answer: ServiceTopology, *, record: bool = True) -> ServiceTopology:
        """Store ``answer`` in the run's ledger and return it unchanged."""
        if record:
            self.ledger.record(answer)
        return answer


def _degraded(service: str, depth: int, reason: str) -> ServiceTopology:
    """Return the answer a query that could not run produces."""
    return ServiceTopology(
        service=service,
        depth=depth,
        dependencies=DependencySet(origin=service, depth=depth),
        dependents=DependencySet(origin=service),
        blast_radius=BlastRadius(origin=service, max_depth=depth),
        searched=False,
        reason=reason,
    )


def dependency_edges(stored: Sequence[TopologyEdge]) -> tuple[DependencyEdge, ...]:
    """Return stored edges as domain edges, dropping any that are not dependencies.

    ``edges_from`` already excludes involvement, so the filter is belt and
    braces — and it is cheap insurance against a backend that one day returns one
    anyway, because the alternative is a ``ValueError`` raised in the middle of a
    reconciliation run.
    """
    edges: list[DependencyEdge] = []
    for edge in stored:
        try:
            edges.append(DependencyEdge.from_stored(edge))
        except ValueError:
            logger.info(
                "topology.skipped_non_dependency_edge",
                from_node=edge.from_node_id,
                to_node=edge.to_node_id,
                kind=edge.kind.value,
            )
    return tuple(edges)


__all__ = [
    "ServiceTopology",
    "TopologyLedger",
    "TopologyQueries",
    "TopologyRecord",
    "check_depth",
    "dependency_edges",
]
