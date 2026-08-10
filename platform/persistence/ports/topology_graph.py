"""Service topology, reachable only through a closed set of bounded traversals.

Eleven shapes, and no method on this port accepts a query string. That is
FR-016 expressed as a signature rather than as a rule somebody has to remember:
there is no way to hand this port Cypher, so there is no way for a model to
generate Cypher that reaches it. The upstream implementation this replaces let
an LLM write its own graph queries, which is an injection surface and a
correctness problem at once — a traversal nobody bounded is a traversal that
returns the whole estate, slowly.

The plan's catalogue names the two writes ``upsert_service`` and
``upsert_dependency``. They are ``upsert_node`` and ``upsert_edge`` here, which
is FR-015's own wording and one generalisation step: episodes are nodes in this
graph too, so ``components_for_episode`` and ``episodes_for_component`` have
something to traverse without another query shape existing to write the link.
Adding a shape is a deliberate act — a row in the plan's table, a contract test,
and a review — and not something a caller can do by composing.

``edges_from`` and ``delete_edge`` are the two that were added deliberately, and
the reason is worth stating because it is the only reason either exists.
Discovery has to *reconcile* rather than replace: keep the operator annotations
on an edge, keep the edges a human drew that no scraper can see, remove the ones
that are genuinely gone. Every traversal above returns *nodes*, so a caller
reading them cannot tell an annotated edge from a bare one, cannot tell an
operator's edge from a scraper's, and has no way to remove one. Reconciliation is
unwritable without these two, and a "soft delete" written through ``upsert_edge``
would not work either — a retired edge still leads a node-returning traversal to
the node behind it.

**Every traversal is bounded twice.** Depth is capped by ``MAX_GRAPH_DEPTH`` and
a request above it raises rather than being clamped, because a blast radius
silently computed at depth 5 when the caller asked for 40 looks complete and is
not. Result size is capped by ``MAX_GRAPH_RESULTS`` and *is* truncated, but the
result says so: ``truncated`` is on every traversal record, and an operator
reading a partial blast radius can see that it is partial.

**Unavailability is raised, not returned empty** (FR-002). A deployment without
Apache AGE keeps working — that is the whole point of the degradation path — but
"this service has no dependents" and "we cannot currently tell you about
dependents" lead to opposite decisions. ``availability`` is how a caller asks
before committing to a plan that needs an answer.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from config.constants.persistence import DEFAULT_GRAPH_DEPTH


class NodeKind(StrEnum):
    """What a node in the topology represents.

    ``EPISODE`` sits alongside the infrastructure kinds because an episode is
    genuinely a node here: it connects to the components it involved, and
    "which incidents has this database been part of" is a traversal rather than
    a join.
    """

    SERVICE = "service"
    DATABASE = "database"
    QUEUE = "queue"
    CACHE = "cache"
    CLUSTER = "cluster"
    EXTERNAL = "external"
    EPISODE = "episode"
    #: A discovered thing the estate is responsible for — a node, a guest, a
    #: datastore, a backup job. One kind rather than one per resource kind,
    #: because resource kinds are extensible by an integration and this
    #: enumeration is not: a traversal must keep working when a deployment
    #: connects a hypervisor nobody here has heard of.
    RESOURCE = "resource"
    #: A network the estate is divided into — the thing every guest inside it
    #: depends on and whose gateway failing takes all of them with it. Distinct
    #: from ``RESOURCE`` because a zone is not something a sweep discovered: it
    #: is a division somebody declared, and a traversal asking "what else is on
    #: this network" must not have to filter resources by an attribute.
    ZONE = "zone"
    #: A document in the knowledge base — a runbook, a post-mortem, a policy.
    #: It sits in the graph for the same reason an episode does: "what has been
    #: written about this thing" is a traversal from the thing, and the
    #: alternative is a join table that duplicates what the graph is for. It is
    #: not infrastructure and nothing depends on it, which is why the edge that
    #: reaches it is excluded from every dependency walk.
    DOCUMENT = "document"


class EdgeKind(StrEnum):
    """What one node's relationship to another means.

    Direction is always "depends on": the edge runs from the thing that would
    break to the thing whose failure would break it. Dependents are found by
    traversing it backwards, which is why blast radius and dependency lookup
    are the same traversal in opposite directions.
    """

    DEPENDS_ON = "depends_on"
    CALLS = "calls"
    READS_FROM = "reads_from"
    WRITES_TO = "writes_to"
    DEPLOYED_ON = "deployed_on"
    INVOLVED = "involved"
    #: A discovered resource runs on another — a guest on a node, a node in a
    #: cluster. Distinct from ``DEPLOYED_ON``, which is a service on
    #: infrastructure a human declared; this one is what a sweep observed.
    HOSTED_ON = "hosted_on"
    #: A backup job protects a resource. The direction is the same as every
    #: other edge here: from the thing that would break to the thing whose
    #: failure would break it, so a datastore's blast radius reaches the job.
    BACKS_UP = "backs_up"
    #: A resource's state is copied to another. Traversed for the same reason
    #: ``BACKS_UP`` is: a replica's failure is a fact about its primary.
    REPLICATES_TO = "replicates_to"
    #: Somebody has written about this resource. From the resource to the
    #: document, which is the direction ``edges_from`` walks and the direction
    #: the question is asked in. **Not a dependency** — a runbook cannot fail,
    #: and a blast radius that reached one would answer "what does this outage
    #: take with it" with a document. It is excluded from every dependency
    #: traversal, exactly as ``INVOLVED`` is and for the same reason.
    DOCUMENTED_BY = "documented_by"


@dataclass(frozen=True, slots=True)
class TopologyNode:
    """One service, datastore, cluster, or episode in the graph."""

    node_id: str
    kind: NodeKind = NodeKind.SERVICE
    name: str = ""
    owner_node_id: str | None = None
    properties: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TopologyEdge:
    """One directed dependency between two nodes."""

    from_node_id: str
    to_node_id: str
    kind: EdgeKind = EdgeKind.DEPENDS_ON
    properties: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TraversalResult:
    """Nodes a traversal reached, and whether the result bound cut it short."""

    nodes: tuple[TopologyNode, ...] = ()
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class BlastRadiusEntry:
    """One node that would be affected, and how many hops away it is."""

    node: TopologyNode
    depth: int


@dataclass(frozen=True, slots=True)
class BlastRadius:
    """What an outage at ``origin_id`` would reach, ordered nearest first.

    Ordering by depth is what makes this usable under pressure. The services one
    hop out are the ones an operator pages; the ones four hops out are context.
    """

    origin_id: str
    max_depth: int
    reaches: tuple[BlastRadiusEntry, ...] = ()
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class TopologyAvailability:
    """Whether topology answers can be given, and why not when they cannot."""

    available: bool
    reason: str | None = None


@runtime_checkable
class TopologyGraph(Protocol):
    """The twelve parameterised shapes, within one tenant."""

    async def availability(self) -> TopologyAvailability:
        """Return whether graph storage is usable right now (FR-002).

        Never raises. This is the method a caller uses to find out whether the
        others will, so it has to answer even when nothing else can.
        """

    async def upsert_node(self, node: TopologyNode) -> TopologyNode:
        """Store ``node``, merging its properties over any existing ones.

        Merge rather than replace: topology arrives from several discovery
        sources, and a Kubernetes scraper that knows a service's namespace
        should not erase the owner a config sync recorded.
        """

    async def upsert_edge(self, edge: TopologyEdge) -> TopologyEdge:
        """Store ``edge``, creating either endpoint if the graph lacks it.

        Endpoints are created as bare nodes rather than rejected. Discovery
        sees an edge before it sees both ends often enough that failing here
        would mean dropping real topology on ordering alone.
        """

    async def edges_from(
        self, node_id: str, *, kinds: Sequence[EdgeKind] = ()
    ) -> tuple[TopologyEdge, ...]:
        """Return the edges leaving ``node_id``, with their stored properties.

        The only method that returns edges rather than nodes, and it exists for
        reconciliation: preserving an operator's annotation and refusing to
        delete an operator's edge both require reading what is on the edge.
        Ordered by target then kind, so two runs over an unchanged graph produce
        the same diff. Bounded by ``MAX_GRAPH_RESULTS``.

        ``kinds`` empty means the dependency edges — what reconciliation asks
        for, and the default because it is the reading that must not change by
        accident when a non-dependency kind is added. Naming kinds returns
        exactly those, including the ones a dependency walk never crosses: that
        is how "which documents is this resource written about in" is asked,
        without the answer also appearing in a blast radius.
        """

    async def delete_edge(self, edge: TopologyEdge) -> bool:
        """Delete the edge with these endpoints and kind, and return whether it existed.

        Endpoints are left in place. A service whose last dependency was retired
        is still a service, and deleting the node would take its annotations,
        its owner, and its environment with it.
        """

    async def direct_dependencies(self, node_id: str) -> TraversalResult:
        """Return what ``node_id`` depends on, one hop out."""

    async def direct_dependents(self, node_id: str) -> TraversalResult:
        """Return what depends on ``node_id``, one hop in."""

    async def transitive_dependencies(
        self,
        node_id: str,
        *,
        depth: int = DEFAULT_GRAPH_DEPTH,
    ) -> TraversalResult:
        """Return everything ``node_id`` depends on within ``depth`` hops.

        The mirror of ``transitive_dependents``, and it exists for the same
        reason the backend rather than the caller should walk: composing it from
        ``direct_dependencies`` means one round trip per node in the frontier,
        which is a query count that grows with the estate to answer a question
        the database can answer in one. The origin is excluded — a cycle would
        otherwise report a service as its own dependency, which is true of the
        graph and useless to an operator.

        Raises ``BoundExceeded`` above ``MAX_GRAPH_DEPTH``.
        """

    async def transitive_dependents(
        self,
        node_id: str,
        *,
        depth: int = DEFAULT_GRAPH_DEPTH,
    ) -> TraversalResult:
        """Return everything that depends on ``node_id`` within ``depth`` hops.

        The set, without distances. Use ``blast_radius`` when the distance
        matters. Raises ``BoundExceeded`` above ``MAX_GRAPH_DEPTH``.
        """

    async def blast_radius(
        self,
        node_id: str,
        *,
        depth: int = DEFAULT_GRAPH_DEPTH,
    ) -> BlastRadius:
        """Return what an outage at ``node_id`` would reach, with hop distances.

        The same traversal as ``transitive_dependents``, answering the question
        an operator actually asks: not "which services", but "which services,
        and how close are they". Raises ``BoundExceeded`` above
        ``MAX_GRAPH_DEPTH``.
        """

    async def shortest_path(
        self,
        from_node_id: str,
        to_node_id: str,
    ) -> tuple[TopologyNode, ...]:
        """Return the shortest dependency path between two nodes, or ``()``.

        Endpoints included. ``()`` means no path within ``MAX_GRAPH_DEPTH``,
        which is not the same as no path at all — and the bound is why this
        returns in a bounded time on a topology that is one large component.
        """

    async def components_for_episode(self, episode_id: str) -> TraversalResult:
        """Return the components an episode involved."""

    async def episodes_for_component(self, node_id: str) -> TraversalResult:
        """Return the episodes that involved ``node_id``, ordered by id."""


__all__ = [
    "BlastRadius",
    "BlastRadiusEntry",
    "EdgeKind",
    "NodeKind",
    "TopologyAvailability",
    "TopologyEdge",
    "TopologyGraph",
    "TopologyNode",
    "TraversalResult",
]
