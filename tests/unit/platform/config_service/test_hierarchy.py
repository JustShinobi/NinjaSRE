"""Tree operations, and the two writes the tree is allowed to refuse.

A node deleted while a child inherits from it, and a reparent that would make a
node its own ancestor, are the two ways an operator turns a hierarchy into
something that cannot be merged. Both are refused here rather than discovered at
resolution time, because at resolution time there is an incident in progress.
"""

from __future__ import annotations

import pytest

from platform.config_service.errors import (
    HierarchyCycle,
    HierarchyTooDeep,
    NodeHasDescendants,
    UnknownNode,
)
from platform.config_service.hierarchy import Hierarchy
from platform.persistence.ports import ConfigNode, ConfigNodeKind

pytestmark = pytest.mark.unit


def node(node_id: str, parent: str | None = None, **values: object) -> ConfigNode:
    """Return a node of the kind its depth implies, which nothing here reads."""
    return ConfigNode(
        node_id=node_id,
        kind=ConfigNodeKind.ORGANISATION if parent is None else ConfigNodeKind.TEAM,
        name=node_id,
        parent_id=parent,
        values=dict(values),
    )


@pytest.fixture
def four_levels() -> Hierarchy:
    return Hierarchy.of(
        [
            node("org"),
            node("division", "org"),
            node("team", "division"),
            node("squad", "team"),
            node("other-team", "division"),
        ]
    )


def test_the_chain_is_root_first_and_inclusive(four_levels: Hierarchy) -> None:
    assert [n.node_id for n in four_levels.chain("squad")] == ["org", "division", "team", "squad"]


def test_the_root_is_its_own_chain(four_levels: Hierarchy) -> None:
    assert [n.node_id for n in four_levels.chain("org")] == ["org"]


def test_children_are_ordered_by_name(four_levels: Hierarchy) -> None:
    assert [n.node_id for n in four_levels.children("division")] == ["other-team", "team"]


def test_descendants_reach_every_depth(four_levels: Hierarchy) -> None:
    assert {n.node_id for n in four_levels.descendants("division")} == {
        "team",
        "squad",
        "other-team",
    }


def test_a_leaf_has_no_descendants(four_levels: Hierarchy) -> None:
    assert four_levels.descendants("squad") == ()


def test_depth_counts_from_the_root(four_levels: Hierarchy) -> None:
    assert four_levels.depth("org") == 0
    assert four_levels.depth("squad") == 3


def test_an_unknown_node_is_named_rather_than_returning_nothing(four_levels: Hierarchy) -> None:
    with pytest.raises(UnknownNode, match="ghost"):
        four_levels.chain("ghost")


def test_the_root_is_the_node_with_no_parent(four_levels: Hierarchy) -> None:
    assert four_levels.root().node_id == "org"


# --- FR-004: deletion and reparenting ----------------------------------------


def test_deleting_a_node_with_descendants_is_refused(four_levels: Hierarchy) -> None:
    with pytest.raises(NodeHasDescendants) as raised:
        four_levels.check_deletable("division")

    assert "division" in str(raised.value)
    assert "team" in str(raised.value)


def test_deleting_a_leaf_is_allowed(four_levels: Hierarchy) -> None:
    four_levels.check_deletable("squad")


def test_reparenting_moves_a_subtree(four_levels: Hierarchy) -> None:
    moved = four_levels.reparent("team", "org")

    assert [n.node_id for n in moved.chain("squad")] == ["org", "team", "squad"]


def test_reparenting_under_a_descendant_would_form_a_cycle(four_levels: Hierarchy) -> None:
    with pytest.raises(HierarchyCycle):
        four_levels.reparent("division", "squad")


def test_a_node_cannot_be_its_own_parent(four_levels: Hierarchy) -> None:
    with pytest.raises(HierarchyCycle):
        four_levels.reparent("team", "team")


def test_the_root_cannot_be_reparented(four_levels: Hierarchy) -> None:
    with pytest.raises(HierarchyCycle):
        four_levels.reparent("org", "team")


def test_a_hierarchy_deeper_than_the_bound_is_refused() -> None:
    chain = [node("n0")] + [node(f"n{i}", f"n{i - 1}") for i in range(1, 40)]

    with pytest.raises(HierarchyTooDeep):
        Hierarchy.of(chain)


def test_a_node_whose_parent_is_missing_is_refused() -> None:
    with pytest.raises(UnknownNode, match="nowhere"):
        Hierarchy.of([node("org"), node("team", "nowhere")])


def test_a_hierarchy_with_two_roots_is_refused() -> None:
    with pytest.raises(HierarchyCycle):
        Hierarchy.of([node("org"), node("other-org")])
