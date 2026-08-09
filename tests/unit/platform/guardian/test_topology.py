"""Two nodes is something you detect, never something you assume.

The cluster this wave was built for has two nodes, and that is exactly why the
shipped set must not presume it. A three-node cluster given two-node warnings
learns to ignore warnings; a single-node installation given cluster detectors
gets an incident about quorum it has no quorum to lose.
"""

from __future__ import annotations

import pytest

from platform.guardian.topology import (
    ClusterShape,
    TopologyRequirement,
    shape_of,
)

pytestmark = pytest.mark.unit


def test_one_node_is_a_single_node_installation() -> None:
    assert shape_of(node_count=1) is ClusterShape.SINGLE_NODE


def test_two_nodes_are_recognised_as_the_two_node_case() -> None:
    assert shape_of(node_count=2) is ClusterShape.TWO_NODE


def test_three_or_more_nodes_are_a_multi_node_cluster() -> None:
    assert shape_of(node_count=3) is ClusterShape.MULTI_NODE
    assert shape_of(node_count=9) is ClusterShape.MULTI_NODE


def test_a_cluster_with_no_nodes_at_all_is_refused_rather_than_guessed() -> None:
    """Zero nodes is a reading that failed, and treating it as single-node would
    silently disable every cluster detector at the moment the API stopped
    answering — which is the moment they matter."""
    with pytest.raises(ValueError, match="no nodes"):
        shape_of(node_count=0)


def test_a_detector_that_needs_a_cluster_does_not_activate_on_one_node() -> None:
    """SC-007."""
    assert not TopologyRequirement.CLUSTERED.activates_on(ClusterShape.SINGLE_NODE)
    assert TopologyRequirement.CLUSTERED.activates_on(ClusterShape.TWO_NODE)
    assert TopologyRequirement.CLUSTERED.activates_on(ClusterShape.MULTI_NODE)


def test_a_two_node_detector_activates_on_two_nodes_and_on_nothing_else() -> None:
    """SC-006."""
    assert TopologyRequirement.TWO_NODE.activates_on(ClusterShape.TWO_NODE)
    assert not TopologyRequirement.TWO_NODE.activates_on(ClusterShape.MULTI_NODE)
    assert not TopologyRequirement.TWO_NODE.activates_on(ClusterShape.SINGLE_NODE)


def test_a_detector_that_needs_nothing_activates_everywhere() -> None:
    """Storage fills and backups fail on a single node exactly as they do on nine."""
    for shape in ClusterShape:
        assert TopologyRequirement.ANY.activates_on(shape)


def test_every_shape_says_what_it_is_in_a_sentence_an_operator_reads() -> None:
    for shape in ClusterShape:
        assert shape.describe().strip()
        assert shape.value in {"single_node", "two_node", "multi_node"}


def test_the_two_node_shape_says_why_it_is_special() -> None:
    """A single node loss costs quorum, and that is the whole reason for the gate."""
    described = ClusterShape.TWO_NODE.describe().lower()

    assert "quorum" in described
