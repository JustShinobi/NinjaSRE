"""Topology from what actually talks: service-mesh traffic, above a noise floor.

A cluster tells you what was declared. A mesh tells you what happened — including
the dependency nobody wrote down, which is reliably the one that causes the
incident nobody expected.

The noise floor is the whole design. Every mesh reports the occasional stray
connection: a health probe that hit the wrong port, a retry that landed
somewhere unexpected, a scanner, a developer's curl. An edge drawn from one of
those is a dependency the agent will reason about and nobody has — and unlike a
missing edge, a wrong one is not obviously wrong when you read it. So an
observation has to clear ``MESH_EDGE_MIN_REQUESTS`` before it becomes topology,
and the request count travels onto the edge as metadata so an operator can see
how strong the signal was.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from config.constants.knowledge import MESH_EDGE_MIN_REQUESTS
from platform.knowledge.topology.discovery.port import DiscoveredTopology, DiscoveryHealth
from platform.knowledge.topology.models import DependencyEdge, DependencyKind, ServiceNode
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: The source name written onto everything this adapter discovers.
SOURCE = "service-mesh"


@dataclass(frozen=True, slots=True)
class ObservedTraffic:
    """One pair of services, and how much one called the other in the window."""

    source_service: str
    destination_service: str
    requests: int = 0
    #: Fraction of those requests that failed, when the mesh reports it. Carried
    #: onto the edge rather than acted on: a dependency that fails half the time
    #: is still a dependency, and an adapter that dropped it would hide exactly
    #: the edge an investigation is about.
    error_ratio: float = 0.0

    def __post_init__(self) -> None:
        if not self.source_service.strip() or not self.destination_service.strip():
            raise ValueError("an observation must name both services")


@runtime_checkable
class MeshTelemetryReader(Protocol):
    """The one read this adapter makes of a service mesh."""

    async def traffic(self) -> Sequence[ObservedTraffic]:
        """Return the service-to-service traffic observed in the current window."""


@dataclass(slots=True)
class ServiceMeshDiscovery:
    """Topology derived from observed traffic between services."""

    reader: MeshTelemetryReader
    minimum_requests: int = MESH_EDGE_MIN_REQUESTS

    @property
    def name(self) -> str:
        """Return the source name written onto everything this discovers."""
        return SOURCE

    async def discover(self) -> DiscoveredTopology:
        """Return the traffic graph above the noise floor, with the read's health.

        A mesh that cannot be read reports ``FAILED`` and nothing else. There is
        no partial state to report: the telemetry query either returns the window
        or it does not, and a query that returned nothing because the mesh was
        unreachable must not be read as "these services stopped talking".
        """
        try:
            observations = await self.reader.traffic()
        except Exception as error:  # noqa: BLE001 — the adapter reports health, never raises
            logger.warning("topology.mesh_read_failed", error=str(error))
            return DiscoveredTopology(
                source=SOURCE, health=DiscoveryHealth.FAILED, reason=str(error)
            )

        nodes: dict[str, ServiceNode] = {}
        edges: dict[tuple[str, str, str], DependencyEdge] = {}
        below_floor = 0

        for observation in observations:
            if observation.requests < self.minimum_requests:
                below_floor += 1
                continue
            for identifier in (observation.source_service, observation.destination_service):
                nodes.setdefault(identifier, ServiceNode(node_id=identifier, source=SOURCE))
            edge = DependencyEdge(
                from_node_id=observation.source_service,
                to_node_id=observation.destination_service,
                kind=DependencyKind.CALLS,
                source=SOURCE,
                metadata={
                    "requests": str(observation.requests),
                    "error_ratio": f"{observation.error_ratio:.4f}",
                },
            )
            edges[edge.key] = edge

        logger.info(
            "topology.mesh_discovered",
            edges=len(edges),
            below_floor=below_floor,
            minimum_requests=self.minimum_requests,
        )
        return DiscoveredTopology(
            source=SOURCE,
            nodes=tuple(nodes.values()),
            edges=tuple(edges.values()),
            health=DiscoveryHealth.HEALTHY,
            covered=tuple(sorted({edge.from_node_id for edge in edges.values()})),
        )


__all__ = [
    "SOURCE",
    "MeshTelemetryReader",
    "ObservedTraffic",
    "ServiceMeshDiscovery",
]
