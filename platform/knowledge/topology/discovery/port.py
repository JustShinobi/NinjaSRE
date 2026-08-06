"""What a discovery source is, and the health signal that makes it safe to re-run.

One method and one dataclass, and the interesting field is ``health``.

A discovery run has three outcomes, not two. It saw the estate; it saw part of
the estate; or it saw nothing because it could not run. Collapsing the middle one
into either of the others is the bug FR-008 exists to prevent — treated as a
complete run, a partial one deletes everything it failed to reach, and treated as
a failure, a partial one throws away the part it did see.

``covered`` is the other half of the same idea. A source reports which nodes it
actually inspected, and reconciliation removes stale edges *only from those*. A
Kubernetes adapter scoped to one namespace should not remove the dependencies of
a service in another namespace it was never looking at, and without ``covered``
there is no way for it to say so.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from platform.knowledge.topology.models import DependencyEdge, ServiceNode


class DiscoveryHealth(StrEnum):
    """How much of the estate a discovery run actually saw."""

    #: Everything the source is scoped to. Absences are real absences.
    HEALTHY = "healthy"

    #: Part of it. Something failed midway, so an absence means "not seen",
    #: which is not the same as "not there".
    DEGRADED = "degraded"

    #: Nothing. The source could not run at all, and has observed no fact about
    #: the estate — not even that a service is unverified.
    FAILED = "failed"

    @property
    def observed(self) -> bool:
        """Return whether this run saw anything worth writing down."""
        return self is not DiscoveryHealth.FAILED

    @property
    def complete(self) -> bool:
        """Return whether an absence in this run's output means the thing is gone."""
        return self is DiscoveryHealth.HEALTHY


@dataclass(frozen=True, slots=True)
class DiscoveredTopology:
    """One discovery run's output: what it saw, how much of it, and where.

    ``covered`` defaults to everything the run named. That is the right default
    for a source scoped to a whole cluster and the wrong one for a source that
    returned half an estate — which is exactly why ``health`` exists beside it,
    and why a degraded run removes nothing whatever ``covered`` says.
    """

    source: str
    nodes: tuple[ServiceNode, ...] = ()
    edges: tuple[DependencyEdge, ...] = ()
    health: DiscoveryHealth = DiscoveryHealth.HEALTHY
    reason: str = ""
    covered: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("a discovery result must name the source that produced it")
        object.__setattr__(self, "source", self.source.strip())
        if not self.covered:
            named = {node.node_id for node in self.nodes}
            named.update(edge.from_node_id for edge in self.edges)
            object.__setattr__(self, "covered", tuple(sorted(named)))

    @property
    def empty(self) -> bool:
        """Return whether the run reported nothing at all."""
        return not self.nodes and not self.edges

    def edges_by_key(self) -> dict[tuple[str, str, str], DependencyEdge]:
        """Return the discovered edges keyed as reconciliation compares them."""
        return {edge.key: edge for edge in self.edges}

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable summary, for a scheduled run's log."""
        return {
            "source": self.source,
            "health": self.health.value,
            "reason": self.reason,
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "covered": list(self.covered),
        }


@runtime_checkable
class DiscoverySource(Protocol):
    """Something that can look at a running estate and report topology."""

    @property
    def name(self) -> str:
        """Return the identifier written onto everything this source discovers."""

    async def discover(self) -> DiscoveredTopology:
        """Return what this source can see right now, with its own health.

        Never raises for an estate it merely could not reach. A source that
        raised would make "the cluster is unreachable" indistinguishable from a
        bug in the adapter, and reconciliation would have to guess which of the
        two it was looking at.
        """


__all__ = [
    "DiscoveredTopology",
    "DiscoveryHealth",
    "DiscoverySource",
]
