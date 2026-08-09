"""How many nodes there are, and which detectors that fact turns on.

Two-node behaviour is detected, never presumed. The cluster this wave was built
for has two nodes; a specification written from it would quietly assume every
cluster does, and the two ways that goes wrong are both bad. A three-node
cluster shown two-node warnings learns that the warnings do not apply to it,
which is how a real one gets ignored. A single-node installation shown cluster
detectors gets an incident about quorum on a machine that has no quorum to lose.

So the shape is a reading, the shape gates the set, and a detector declares what
it needs rather than the set being filtered somewhere else. Three requirements
cover every shipped detector: most need nothing at all, some need more than one
node to be meaningful, and two are specifically about the arithmetic of two.

**Zero nodes is refused rather than treated as one.** A cluster read that came
back empty is a reading that failed, and mapping it to the single-node shape
would disable every cluster detector at precisely the moment the API stopped
answering.
"""

from __future__ import annotations

from enum import StrEnum

from config.constants.guardian import (
    CLUSTER_SHAPE_MULTI_NODE,
    CLUSTER_SHAPE_SINGLE_NODE,
    CLUSTER_SHAPE_TWO_NODE,
    TWO_NODE_NODE_COUNT,
)


class ClusterShape(StrEnum):
    """How many nodes this deployment is watching, as a fact detectors read."""

    #: One node. There is no cluster, so there is nothing to lose quorum over.
    SINGLE_NODE = CLUSTER_SHAPE_SINGLE_NODE
    #: Exactly two. Quorum needs both, so a single node loss makes the survivor
    #: unable to write ``/etc/pve`` — the finding this wave exists to catch.
    TWO_NODE = CLUSTER_SHAPE_TWO_NODE
    #: Three or more, where losing one node leaves a quorate remainder.
    MULTI_NODE = CLUSTER_SHAPE_MULTI_NODE

    def describe(self) -> str:
        """Return the sentence an operator reads beside this shape."""
        return _SHAPE_DESCRIPTIONS[self]

    @property
    def clustered(self) -> bool:
        """Return whether more than one node is participating."""
        return self is not ClusterShape.SINGLE_NODE


_SHAPE_DESCRIPTIONS: dict[ClusterShape, str] = {
    ClusterShape.SINGLE_NODE: (
        "One node. Cluster detectors are not active, because there is no membership to "
        "lose and no link to degrade; storage, guest, backup and maintenance detectors "
        "all apply exactly as they would on nine nodes."
    ),
    ClusterShape.TWO_NODE: (
        "Two nodes, which is the shape where quorum needs both of them. Losing either "
        "one drops the survivor below quorum: the cluster filesystem goes read-only, "
        "nothing can be started, stopped or migrated, and the guests already running "
        "carry on running. The two-node detectors exist to say whether that is "
        "mitigated — by a quorum device that actually votes, by two_node, or by "
        "neither."
    ),
    ClusterShape.MULTI_NODE: (
        "Three or more nodes, so losing one leaves a quorate remainder. The two-node "
        "detectors do not apply and are not activated."
    ),
}


class TopologyRequirement(StrEnum):
    """What a detector needs to be true before it is worth activating."""

    #: Nothing. Storage fills and backups fail identically at every size.
    ANY = "any"
    #: More than one node. Quorum, corosync links, fencing, version divergence.
    CLUSTERED = "clustered"
    #: Exactly two. The arithmetic of quorum with an even, minimal membership.
    TWO_NODE = "two_node"

    def activates_on(self, shape: ClusterShape) -> bool:
        """Return whether a detector with this requirement runs against ``shape``."""
        match self:
            case TopologyRequirement.ANY:
                return True
            case TopologyRequirement.CLUSTERED:
                return shape.clustered
            case TopologyRequirement.TWO_NODE:
                return shape is ClusterShape.TWO_NODE


def shape_of(*, node_count: int) -> ClusterShape:
    """Return the shape ``node_count`` nodes make.

    Raises ``ValueError`` for a count below one: a cluster read that returned no
    nodes is a failed read, and calling it single-node would turn off every
    cluster detector at the moment the API stopped answering.
    """
    if node_count < 1:
        raise ValueError(
            "a cluster reading with no nodes in it is a reading that failed, not a "
            "single-node installation; refusing rather than disabling every cluster "
            "detector at the moment the API stopped answering"
        )
    if node_count == 1:
        return ClusterShape.SINGLE_NODE
    if node_count == TWO_NODE_NODE_COUNT:
        return ClusterShape.TWO_NODE
    return ClusterShape.MULTI_NODE


__all__ = ["ClusterShape", "TopologyRequirement", "shape_of"]
