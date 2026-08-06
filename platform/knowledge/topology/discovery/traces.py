"""Topology from distributed traces: what talks *within one request*.

The mesh answers "do these two services communicate". Traces answer something
narrower and more useful for an incident: whether one service is on the critical
path of the other's request. A nightly batch job and a checkout call both show up
as traffic; only one of them explains a user-facing latency spike, and the parent
relationship in a span tree is what distinguishes them.

The same noise floor applies, for the same reason and with a sharper edge: a
single span between two services is more often an experiment, a one-off script,
or a misconfigured client than an architecture. ``TRACE_EDGE_MIN_SPANS`` is what
keeps those out, and the span count travels onto the edge so an operator can see
how strong the evidence was.

Latency is carried but never filtered on. A dependency that is slow is still a
dependency — and it is usually the one the investigation is about.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from config.constants.knowledge import TRACE_EDGE_MIN_SPANS
from platform.knowledge.topology.discovery.port import DiscoveredTopology, DiscoveryHealth
from platform.knowledge.topology.models import DependencyEdge, DependencyKind, ServiceNode
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: The source name written onto everything this adapter discovers.
SOURCE = "traces"


@dataclass(frozen=True, slots=True)
class ObservedSpanEdge:
    """One parent-child service relationship, as the trace store aggregates it."""

    parent_service: str
    child_service: str
    spans: int = 0
    #: The 95th-percentile duration of the child span, in milliseconds, when the
    #: trace store reports one. Carried onto the edge for a reader; never used to
    #: decide whether the edge exists.
    p95_latency_ms: float = 0.0

    def __post_init__(self) -> None:
        if not self.parent_service.strip() or not self.child_service.strip():
            raise ValueError("a span edge must name both services")


@runtime_checkable
class TraceReader(Protocol):
    """The one read this adapter makes of a trace store."""

    async def span_edges(self) -> Sequence[ObservedSpanEdge]:
        """Return the parent-child service pairs seen in the current window."""


@dataclass(slots=True)
class TraceDiscovery:
    """Topology derived from the shape of traced requests."""

    reader: TraceReader
    minimum_spans: int = TRACE_EDGE_MIN_SPANS

    @property
    def name(self) -> str:
        """Return the source name written onto everything this discovers."""
        return SOURCE

    async def discover(self) -> DiscoveredTopology:
        """Return the request graph above the noise floor, with the read's health.

        A trace store covers only what is instrumented, which is why a healthy
        run from this source is still not a complete picture of the estate — and
        why ``covered`` names only the services that appeared as a parent. A
        service nobody traced has not been observed to have no dependencies.
        """
        try:
            observations = await self.reader.span_edges()
        except Exception as error:  # noqa: BLE001 — the adapter reports health, never raises
            logger.warning("topology.trace_read_failed", error=str(error))
            return DiscoveredTopology(
                source=SOURCE, health=DiscoveryHealth.FAILED, reason=str(error)
            )

        nodes: dict[str, ServiceNode] = {}
        edges: dict[tuple[str, str, str], DependencyEdge] = {}
        below_floor = 0

        for observation in observations:
            if observation.spans < self.minimum_spans:
                below_floor += 1
                continue
            if observation.parent_service == observation.child_service:
                # A service calling itself is an internal span, not topology.
                continue
            for identifier in (observation.parent_service, observation.child_service):
                nodes.setdefault(identifier, ServiceNode(node_id=identifier, source=SOURCE))
            edge = DependencyEdge(
                from_node_id=observation.parent_service,
                to_node_id=observation.child_service,
                kind=DependencyKind.CALLS,
                source=SOURCE,
                metadata={
                    "spans": str(observation.spans),
                    "p95_latency_ms": f"{observation.p95_latency_ms:.1f}",
                },
            )
            edges[edge.key] = edge

        logger.info(
            "topology.traces_discovered",
            edges=len(edges),
            below_floor=below_floor,
            minimum_spans=self.minimum_spans,
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
    "ObservedSpanEdge",
    "TraceDiscovery",
    "TraceReader",
]
