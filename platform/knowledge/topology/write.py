"""The primitive writes: manual entry, annotation, and removal.

Everything that changes the graph goes through here — the operator typing a
dependency into a console, the declarative import, and reconciliation applying a
discovery run. One place, because three things have to be true of every write and
each of them is easy to forget once:

**A write stamps when it happened.** ``verified_at`` is what a later reader
discounts a stale edge by, and an edge written without one is indistinguishable
from one nobody has confirmed since the deployment started.

**An operator's write is marked as one.** Discovery removes what it cannot see,
and the flag is the only thing standing between that rule and a failover path a
human drew being deleted by a scraper that was never going to observe it.

**Merging is the store's job, and annotations are merged on top.** ``upsert_node``
merges properties, so a discovery run that knows a namespace does not erase the
owner a config sync recorded. Annotations are read, merged, and written back here
rather than trusted to that merge, because the stored form is one property and a
whole-property overwrite would take every annotation with it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime

from platform.knowledge.clock import now as _utc_now
from platform.knowledge.errors import UnknownDependency
from platform.knowledge.topology.models import (
    OPERATOR_SOURCE,
    DependencyEdge,
    DependencyKind,
    ServiceNode,
    clean_annotations,
)
from platform.knowledge.topology.queries import dependency_edges
from platform.observability.logging import get_logger
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope, UnitOfWork

logger = get_logger(__name__)


@dataclass(slots=True)
class TopologyWriter:
    """Manual entry, annotation, and removal, for one team's graph."""

    gateway: PersistenceGateway
    scope: TenantScope
    clock: Callable[[], datetime] = _utc_now

    async def upsert_service(self, service: ServiceNode) -> ServiceNode:
        """Store ``service``, stamped and attributed, and return what was stored."""
        async with self.gateway.begin(self.scope) as uow:
            return await self.write_service(uow, service)

    async def upsert_dependency(self, edge: DependencyEdge) -> DependencyEdge:
        """Store ``edge``, creating either endpoint the graph lacks."""
        async with self.gateway.begin(self.scope) as uow:
            return await self.write_dependency(uow, edge)

    async def annotate_service(self, node_id: str, annotations: Mapping[str, str]) -> ServiceNode:
        """Merge ``annotations`` onto a service and return it.

        Creates the service if the graph has never seen it. Annotating something
        that does not exist yet is how an operator records what they know about a
        system before any discovery source reaches it, and refusing would make
        the graph unusable for exactly the estate that most needs hand-entry.
        """
        stamped = replace(
            ServiceNode(node_id=node_id, annotations=annotations),
            source=OPERATOR_SOURCE,
            operator_authored=True,
        )
        async with self.gateway.begin(self.scope) as uow:
            return await self.write_service(uow, stamped)

    async def annotate_dependency(
        self,
        from_node_id: str,
        to_node_id: str,
        kind: DependencyKind,
        annotations: Mapping[str, str],
    ) -> DependencyEdge:
        """Merge ``annotations`` onto an existing dependency and return it.

        Raises ``UnknownDependency`` when the edge does not exist — unlike a
        service, which is created. An operator annotating a dependency they
        believe exists has either mistyped it or is looking at a graph that has
        moved, and creating it on their behalf would turn a typo into topology
        that discovery then declines to remove.
        """
        cleaned = clean_annotations(annotations)
        async with self.gateway.begin(self.scope) as uow:
            existing = {
                edge.key: edge
                for edge in dependency_edges(await uow.topology.edges_from(from_node_id))
            }
            found = existing.get((from_node_id, to_node_id, kind.value))
            if found is None:
                raise UnknownDependency(from_node_id, to_node_id, kind.value)

            merged = replace(found, annotations={**found.annotations, **cleaned})
            await uow.topology.upsert_edge(merged.to_stored())

        logger.info(
            "topology.dependency_annotated",
            from_node=from_node_id,
            to_node=to_node_id,
            kind=kind.value,
            annotations=len(merged.annotations),
        )
        return merged

    async def remove_dependency(self, edge: DependencyEdge) -> bool:
        """Delete one dependency and return whether it existed.

        Endpoints are left alone. A service whose last dependency was retired is
        still a service, and taking the node would take its annotations with it.
        """
        async with self.gateway.begin(self.scope) as uow:
            removed = await uow.topology.delete_edge(edge.to_stored())
        if removed:
            logger.info(
                "topology.dependency_removed",
                from_node=edge.from_node_id,
                to_node=edge.to_node_id,
                kind=edge.kind.value,
            )
        return removed

    # -- inside a caller's unit of work ----------------------------------------
    #
    # Reconciliation writes dozens of records in one transaction. These two are
    # the halves that take an open unit of work, so a batch is one transaction
    # rather than one per record — a half-applied discovery run is the state
    # that produces a wrong blast radius nobody can explain afterwards.

    async def write_service(self, uow: UnitOfWork, service: ServiceNode) -> ServiceNode:
        """Store one service inside an open unit of work."""
        stamped = _stamped(service, self.clock())
        stored = await uow.topology.upsert_node(stamped.to_stored())
        return ServiceNode.from_stored(stored)

    async def write_dependency(self, uow: UnitOfWork, edge: DependencyEdge) -> DependencyEdge:
        """Store one dependency inside an open unit of work, keeping annotations.

        The existing edge is read first so its annotations survive. The store
        merges *properties*, and the annotations live inside one of them — a
        whole-property write would take every annotation with it, which is the
        exact failure SC-003 exists to catch.
        """
        moment = self.clock()
        existing = {
            found.key: found
            for found in dependency_edges(await uow.topology.edges_from(edge.from_node_id))
        }
        previous = existing.get(edge.key)
        merged = _stamped_edge(edge, moment)
        if previous is not None:
            merged = replace(
                merged,
                annotations={**previous.annotations, **merged.annotations},
                metadata={**previous.metadata, **merged.metadata},
                operator_authored=previous.operator_authored or merged.operator_authored,
            )

        stored = await uow.topology.upsert_edge(merged.to_stored())
        return DependencyEdge.from_stored(stored)


def _stamped(service: ServiceNode, moment: datetime) -> ServiceNode:
    """Return ``service`` with its verification stamp and attribution filled in."""
    return replace(
        service,
        verified_at=service.verified_at or moment,
        operator_authored=service.operator_authored or service.source == OPERATOR_SOURCE,
    )


def _stamped_edge(edge: DependencyEdge, moment: datetime) -> DependencyEdge:
    """Return ``edge`` with its verification stamp and attribution filled in."""
    return replace(
        edge,
        verified_at=edge.verified_at or moment,
        operator_authored=edge.operator_authored or edge.source == OPERATOR_SOURCE,
    )


@dataclass(slots=True)
class TopologyWriteReport:
    """What one batch of writes did, for an import or a discovery run to report."""

    services: int = 0
    dependencies: int = 0
    problems: tuple[str, ...] = field(default_factory=tuple)

    @property
    def total(self) -> int:
        """Return how many records were written in all."""
        return self.services + self.dependencies


__all__ = ["TopologyWriteReport", "TopologyWriter"]
