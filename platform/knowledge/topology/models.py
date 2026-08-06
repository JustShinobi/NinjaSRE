"""Services and dependencies as this tier reasons about them, and the storage shapes.

``platform.persistence.ports.topology_graph`` holds the *stored* shapes:
``TopologyNode`` and ``TopologyEdge``, which are deliberately thin — an id, a
kind, a name, and an untyped property bag. The types here are the *domain*
records: an environment, an owner, operator annotations, a verification stamp,
and the provenance of whichever discovery source last saw the thing. This module
owns the translation between them, in one place, so the storage layer never
learns what an operator annotation is and nothing above it has to remember which
fields live in the property bag.

Three definitions are worth reading before anything else.

**An annotation is an operator's writing, and discovery never overwrites one.**
That is the property reconciliation is built around: a team that wrote "this
dependency is only used during failover" on an edge must find it there after
every subsequent discovery run, or they stop writing them. Annotations therefore
travel on the record rather than in the same bag as discovered properties, and
the merge that reconciliation performs treats the two halves differently.

**``verified_at`` means a discovery source observed this, not that it is
correct.** Hand-entered topology has no verification stamp and is not thereby
wrong; a stale stamp means nobody has looked recently. Both are reported beside
every result so the agent can discount an edge rather than trusting it equally.

**``unverified`` is what a partially-failed discovery leaves behind** (FR-008).
A source that could not see part of the estate marks what it could not confirm
instead of deleting it, because a Kubernetes API having a bad minute must not
delete a team's topology. Unverified is a label on something that is still there.

Direction, throughout, is "depends on": an edge runs from the thing that would
break to the thing whose failure would break it. Dependents are the same edges
read backwards, which is why blast radius and dependency lookup are one traversal
in two directions.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import Any

from config.constants.knowledge import (
    MAX_ANNOTATION_CHARS,
    MAX_TOPOLOGY_ANNOTATIONS,
    TOPOLOGY_VERIFICATION_STALE_DAYS,
)
from platform.knowledge.clock import is_stale
from platform.persistence.ports.topology_graph import (
    EdgeKind,
    NodeKind,
    TopologyEdge,
    TopologyNode,
)

#: Keys this tier keeps inside the stored property bag. Named constants because
#: the writer and the reader are different modules, and a key that is spelled two
#: ways does not fail — it reads back as an absent annotation, which looks like
#: an operator who never wrote one.
ENVIRONMENT_KEY = "environment"
ANNOTATIONS_KEY = "annotations"
SOURCE_KEY = "discovered_by"
VERIFIED_AT_KEY = "verified_at"
UNVERIFIED_KEY = "unverified"
OPERATOR_AUTHORED_KEY = "operator_authored"
METADATA_KEY = "metadata"

#: What a manually entered or file-imported record records as its source. A real
#: value rather than an empty string, so "nobody discovered this" is a statement
#: in the data rather than an absence a reader has to interpret.
OPERATOR_SOURCE = "operator"


class DependencyKind(StrEnum):
    """What one service's dependency on another consists of (FR-002).

    Five kinds, and the distinction earns its place at exactly one moment: an
    investigation into slow checkouts treats ``calls`` and ``reads_from``
    differently from ``deploys_to``, because the first two carry request latency
    and the third carries a blast radius that only matters during a rollout.
    """

    DEPENDS_ON = "depends_on"
    CALLS = "calls"
    READS_FROM = "reads_from"
    WRITES_TO = "writes_to"
    DEPLOYS_TO = "deploys_to"

    @property
    def edge_kind(self) -> EdgeKind:
        """Return the stored edge kind this domain kind maps to."""
        return _EDGE_KINDS[self]

    @classmethod
    def from_edge_kind(cls, kind: EdgeKind) -> DependencyKind:
        """Return the domain kind a stored edge kind describes.

        ``involved`` has no domain kind and raises. It attaches an episode to the
        components it touched, and reading one as a dependency would make every
        service that ever appeared in an incident a dependency of every other one
        that did.
        """
        found = _DOMAIN_KINDS.get(kind)
        if found is None:
            raise ValueError(
                f"{kind.value!r} is not a dependency — an involvement edge links an "
                "episode to a component and is not a relationship between services"
            )
        return found

    @classmethod
    def parse(cls, value: str) -> DependencyKind:
        """Return the kind ``value`` names, or ``DEPENDS_ON``.

        An unrecognised kind degrades to the general one rather than raising: a
        discovery adapter that learns a vendor's new relationship name should
        record the edge, and a dependency of unstated kind is still a dependency.
        """
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            return cls.DEPENDS_ON


_EDGE_KINDS: dict[DependencyKind, EdgeKind] = {
    DependencyKind.DEPENDS_ON: EdgeKind.DEPENDS_ON,
    DependencyKind.CALLS: EdgeKind.CALLS,
    DependencyKind.READS_FROM: EdgeKind.READS_FROM,
    DependencyKind.WRITES_TO: EdgeKind.WRITES_TO,
    DependencyKind.DEPLOYS_TO: EdgeKind.DEPLOYED_ON,
}

_DOMAIN_KINDS: dict[EdgeKind, DependencyKind] = {
    stored: domain for domain, stored in _EDGE_KINDS.items()
}


def clean_annotations(annotations: Mapping[str, str]) -> dict[str, str]:
    """Return ``annotations`` stripped, bounded, and in first-seen order.

    Both bounds bite at the tail rather than raising. An operator who pastes a
    post-mortem into an annotation should lose the paste, not the node — and a
    discovery run that refused to store a service because somebody over-annotated
    it would be a topology gap caused by documentation.
    """
    cleaned: dict[str, str] = {}
    for key, value in annotations.items():
        name = str(key).strip()
        if not name or name in cleaned:
            continue
        cleaned[name] = str(value).strip()[:MAX_ANNOTATION_CHARS]
        if len(cleaned) >= MAX_TOPOLOGY_ANNOTATIONS:
            break
    return cleaned


def _text_map(value: Any) -> dict[str, str]:
    """Return a stored property read back as a string-keyed map."""
    if not isinstance(value, Mapping):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def _moment(value: Any) -> datetime | None:
    """Return a stored ISO instant, or ``None`` when it is absent or unreadable.

    Unreadable degrades to absent, and absent is treated as unverified — which is
    the conservative direction. A corrupt timestamp read as "just now" would
    report a service as freshly confirmed on the strength of a parse failure.
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class ServiceNode:
    """One service, datastore, queue, cluster, or external system (FR-001)."""

    node_id: str
    kind: NodeKind = NodeKind.SERVICE
    name: str = ""
    environment: str = ""
    owner: str = ""
    annotations: Mapping[str, str] = field(default_factory=dict)
    source: str = OPERATOR_SOURCE
    operator_authored: bool = False
    verified_at: datetime | None = None
    unverified: bool = False

    def __post_init__(self) -> None:
        if not self.node_id.strip():
            raise ValueError("a service node must have an id")
        object.__setattr__(self, "node_id", self.node_id.strip())
        object.__setattr__(self, "name", self.name.strip() or self.node_id)
        object.__setattr__(self, "annotations", clean_annotations(self.annotations))

    def stale_at(self, moment: datetime) -> bool:
        """Return whether nothing has verified this node recently enough.

        Operator-authored nodes are never stale. Nobody re-observes a thing a
        human wrote down, and reporting an operator's own entry as unverified
        would train them to ignore the label everywhere else it appears.
        """
        if self.operator_authored:
            return False
        return self.unverified or is_stale(
            self.verified_at, at=moment, after_days=TOPOLOGY_VERIFICATION_STALE_DAYS
        )

    def with_annotations(self, annotations: Mapping[str, str]) -> ServiceNode:
        """Return this node carrying ``annotations`` merged over its own."""
        return replace(self, annotations={**self.annotations, **annotations})

    def to_stored(self) -> TopologyNode:
        """Return this node in the shape ``TopologyGraph`` persists."""
        return TopologyNode(
            node_id=self.node_id,
            kind=self.kind,
            name=self.name,
            owner_node_id=self.owner or None,
            properties={
                ENVIRONMENT_KEY: self.environment,
                ANNOTATIONS_KEY: dict(self.annotations),
                SOURCE_KEY: self.source,
                OPERATOR_AUTHORED_KEY: self.operator_authored,
                VERIFIED_AT_KEY: self.verified_at.isoformat() if self.verified_at else "",
                UNVERIFIED_KEY: self.unverified,
            },
        )

    @classmethod
    def from_stored(cls, stored: TopologyNode) -> ServiceNode:
        """Return the domain node a stored record describes."""
        properties = dict(stored.properties)
        return cls(
            node_id=stored.node_id,
            kind=stored.kind,
            name=stored.name,
            environment=str(properties.get(ENVIRONMENT_KEY, "")),
            owner=stored.owner_node_id or "",
            annotations=_text_map(properties.get(ANNOTATIONS_KEY)),
            source=str(properties.get(SOURCE_KEY, OPERATOR_SOURCE)),
            operator_authored=bool(properties.get(OPERATOR_AUTHORED_KEY, False)),
            verified_at=_moment(properties.get(VERIFIED_AT_KEY)),
            unverified=bool(properties.get(UNVERIFIED_KEY, False)),
        )


@dataclass(frozen=True, slots=True)
class DependencyEdge:
    """One directed dependency, with what discovery knows about it (FR-002).

    ``operator_authored`` is the flag reconciliation reads before it removes
    anything. An edge a human drew is one no discovery source can see — a
    failover path, a batch job's input, a dependency that only exists during a
    release — and removing it because a scraper did not report it would delete
    exactly the knowledge that could not have been discovered.
    """

    from_node_id: str
    to_node_id: str
    kind: DependencyKind = DependencyKind.DEPENDS_ON
    metadata: Mapping[str, str] = field(default_factory=dict)
    annotations: Mapping[str, str] = field(default_factory=dict)
    source: str = OPERATOR_SOURCE
    operator_authored: bool = False
    verified_at: datetime | None = None
    unverified: bool = False

    def __post_init__(self) -> None:
        if not self.from_node_id.strip() or not self.to_node_id.strip():
            raise ValueError("a dependency edge must name both endpoints")
        if self.from_node_id.strip() == self.to_node_id.strip():
            raise ValueError(
                f"{self.from_node_id!r} cannot depend on itself — a self-edge is a "
                "traversal that never terminates for no information"
            )
        object.__setattr__(self, "from_node_id", self.from_node_id.strip())
        object.__setattr__(self, "to_node_id", self.to_node_id.strip())
        object.__setattr__(self, "annotations", clean_annotations(self.annotations))

    @property
    def key(self) -> tuple[str, str, str]:
        """Return what identifies this edge: both endpoints and the kind.

        The kind is part of the identity because two services can genuinely
        relate twice — a service that both calls an API and reads its database
        has two dependencies, and collapsing them would lose one on every
        reconciliation.
        """
        return (self.from_node_id, self.to_node_id, self.kind.value)

    def stale_at(self, moment: datetime) -> bool:
        """Return whether nothing has verified this edge recently enough."""
        if self.operator_authored:
            return False
        return self.unverified or is_stale(
            self.verified_at, at=moment, after_days=TOPOLOGY_VERIFICATION_STALE_DAYS
        )

    def verified(self, moment: datetime, *, source: str) -> DependencyEdge:
        """Return this edge stamped as observed by ``source`` at ``moment``."""
        return replace(self, verified_at=moment, unverified=False, source=source)

    def marked_unverified(self) -> DependencyEdge:
        """Return this edge flagged as something discovery could not confirm.

        The verification stamp is kept. When it was last seen is the fact a
        reader needs in order to decide how much the edge is worth, and clearing
        it would turn "we could not check today" into "nobody has ever checked".
        """
        return replace(self, unverified=True)

    def to_stored(self) -> TopologyEdge:
        """Return this edge in the shape ``TopologyGraph`` persists."""
        return TopologyEdge(
            from_node_id=self.from_node_id,
            to_node_id=self.to_node_id,
            kind=self.kind.edge_kind,
            properties={
                METADATA_KEY: dict(self.metadata),
                ANNOTATIONS_KEY: dict(self.annotations),
                SOURCE_KEY: self.source,
                OPERATOR_AUTHORED_KEY: self.operator_authored,
                VERIFIED_AT_KEY: self.verified_at.isoformat() if self.verified_at else "",
                UNVERIFIED_KEY: self.unverified,
            },
        )

    @classmethod
    def from_stored(cls, stored: TopologyEdge) -> DependencyEdge:
        """Return the domain edge a stored record describes."""
        properties = dict(stored.properties)
        return cls(
            from_node_id=stored.from_node_id,
            to_node_id=stored.to_node_id,
            kind=DependencyKind.from_edge_kind(stored.kind),
            metadata=_text_map(properties.get(METADATA_KEY)),
            annotations=_text_map(properties.get(ANNOTATIONS_KEY)),
            source=str(properties.get(SOURCE_KEY, OPERATOR_SOURCE)),
            operator_authored=bool(properties.get(OPERATOR_AUTHORED_KEY, False)),
            verified_at=_moment(properties.get(VERIFIED_AT_KEY)),
            unverified=bool(properties.get(UNVERIFIED_KEY, False)),
        )


@dataclass(frozen=True, slots=True)
class ReachedService:
    """One service a traversal reached, and how many hops away it is."""

    service: ServiceNode
    depth: int


@dataclass(frozen=True, slots=True)
class BlastRadius:
    """What an outage at ``origin`` would reach, nearest first (FR-004).

    ``truncated`` is on the record rather than inferred from the count, because
    the two answers "nothing else is affected" and "we stopped counting" lead an
    operator to write different incident updates, and a caller comparing
    ``len(reaches)`` against a bound would be reimplementing the check that
    storage already made.
    """

    origin: str
    max_depth: int
    reaches: tuple[ReachedService, ...] = ()
    truncated: bool = False

    @property
    def empty(self) -> bool:
        """Return whether nothing depends on the origin within the bound."""
        return not self.reaches

    @property
    def services(self) -> tuple[ServiceNode, ...]:
        """Return the reached services alone, still nearest first."""
        return tuple(entry.service for entry in self.reaches)


@dataclass(frozen=True, slots=True)
class DependencySet:
    """The services one traversal returned, in one direction, bounded."""

    origin: str
    services: tuple[ServiceNode, ...] = ()
    truncated: bool = False
    depth: int = 1

    @property
    def empty(self) -> bool:
        """Return whether the traversal reached nothing."""
        return not self.services

    def names(self) -> tuple[str, ...]:
        """Return the reached node ids, in the order the traversal gave them."""
        return tuple(service.node_id for service in self.services)


def service_nodes(stored: Iterable[TopologyNode]) -> tuple[ServiceNode, ...]:
    """Return stored nodes as domain nodes, in order."""
    return tuple(ServiceNode.from_stored(node) for node in stored)


__all__ = [
    "ANNOTATIONS_KEY",
    "ENVIRONMENT_KEY",
    "METADATA_KEY",
    "OPERATOR_AUTHORED_KEY",
    "OPERATOR_SOURCE",
    "SOURCE_KEY",
    "UNVERIFIED_KEY",
    "VERIFIED_AT_KEY",
    "BlastRadius",
    "DependencyEdge",
    "DependencyKind",
    "DependencySet",
    "ReachedService",
    "ServiceNode",
    "clean_annotations",
    "service_nodes",
]
