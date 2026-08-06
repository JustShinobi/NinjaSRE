"""Who else the change reaches — the question a reviewer asks before the diff.

"This changes the masking level" and "this changes the masking level for
nineteen teams" are the same diff and different decisions. The blast radius is
what makes the second one visible, and it is meant to be shown *above* the diff:
the stakes decide how carefully somebody reads, and a reviewer who learns the
scope afterwards has already decided how much attention to spend.

The subtle half is the exclusion. A team that sets its own value for the path is
not affected by an ancestor changing it, and counting them would inflate every
radius until the number meant nothing. They are counted separately instead,
because "somebody already disagreed with this value" is the reviewer's other
question.
"""

from __future__ import annotations

import pytest

from platform.approvals.blast_radius import compute
from platform.config_service.document import NodeDocument
from platform.config_service.hierarchy import Hierarchy
from platform.persistence.ports import ConfigNode, ConfigNodeKind

pytestmark = pytest.mark.unit

ORG = "acme"
DIVISION = "division-platform"
PAYMENTS = "team-payments"
SEARCH = "team-search"
CHECKOUT = "squad-checkout"


def node(
    node_id: str,
    parent_id: str | None,
    *,
    kind: ConfigNodeKind = ConfigNodeKind.TEAM,
    settings: dict[str, object] | None = None,
) -> ConfigNode:
    """Return one node of the tree, optionally overriding something."""
    return ConfigNode(
        node_id=node_id,
        kind=kind,
        name=node_id,
        parent_id=parent_id,
        values=NodeDocument.of(settings or {}).to_values(),
    )


@pytest.fixture
def tree() -> Hierarchy:
    """Return a four-level tree with two teams under one division."""
    return Hierarchy.of(
        [
            node(ORG, None, kind=ConfigNodeKind.ORGANISATION),
            node(DIVISION, ORG),
            node(PAYMENTS, DIVISION),
            node(SEARCH, DIVISION),
            node(CHECKOUT, PAYMENTS, kind=ConfigNodeKind.SERVICE),
        ]
    )


def test_a_leaf_change_reaches_nothing_beneath_it(tree: Hierarchy) -> None:
    radius = compute(tree, CHECKOUT)

    assert radius.is_local
    assert radius.affected == ()
    assert "nothing beneath it" in radius.describe()


def test_a_division_change_reaches_every_team_beneath_it(tree: Hierarchy) -> None:
    radius = compute(tree, DIVISION)

    assert set(radius.affected) == {PAYMENTS, SEARCH, CHECKOUT}
    assert radius.affected_count == 3
    assert set(radius.teams) == {PAYMENTS, SEARCH}
    assert radius.team_count == 2


def test_the_description_names_the_teams_a_reviewer_would_recognise(
    tree: Hierarchy,
) -> None:
    described = compute(tree, DIVISION).describe()

    assert PAYMENTS in described
    assert "3 node(s)" in described


def test_a_change_at_the_organisation_reaches_the_whole_tree(tree: Hierarchy) -> None:
    radius = compute(tree, None)

    assert radius.affected_count == 4
    assert radius.node_id is None


def test_a_node_that_overrides_the_path_is_excluded_and_counted() -> None:
    tree = Hierarchy.of(
        [
            node(ORG, None, kind=ConfigNodeKind.ORGANISATION),
            node(DIVISION, ORG),
            node(PAYMENTS, DIVISION, settings={"policies": {"masking": {"level": "off"}}}),
            node(SEARCH, DIVISION),
        ]
    )

    radius = compute(tree, DIVISION, path="policies.masking.level")

    assert radius.affected == (SEARCH,)
    assert radius.overriding == (PAYMENTS,)
    assert "already set their own value" in radius.describe()


def test_overriding_a_parent_path_shields_the_child_path() -> None:
    """A node setting ``policies.masking`` overrides a change to its ``level``."""
    tree = Hierarchy.of(
        [
            node(ORG, None, kind=ConfigNodeKind.ORGANISATION),
            node(PAYMENTS, ORG, settings={"policies": {"masking": {"level": "off"}}}),
        ]
    )

    radius = compute(tree, ORG, path="policies.masking.level")

    assert radius.overriding == (PAYMENTS,)


def test_overriding_a_child_path_does_not_shield_the_parent_path() -> None:
    """The other direction: setting the level does not shield a change to policies."""
    tree = Hierarchy.of(
        [
            node(ORG, None, kind=ConfigNodeKind.ORGANISATION),
            node(PAYMENTS, ORG, settings={"policies": {"masking": {"level": "off"}}}),
        ]
    )

    radius = compute(tree, ORG, path="policies")

    assert radius.affected == (PAYMENTS,)
    assert radius.overriding == ()


def test_without_a_path_every_descendant_is_affected(tree: Hierarchy) -> None:
    """The honest answer when the path is unknown. A narrow guess would be trusted."""
    radius = compute(tree, DIVISION)

    assert radius.overriding == ()
    assert radius.affected_count == 3


def test_a_long_list_is_capped_and_says_so() -> None:
    tree = Hierarchy.of(
        [
            node(ORG, None, kind=ConfigNodeKind.ORGANISATION),
            *(node(f"team-{index}", ORG) for index in range(50)),
        ]
    )

    radius = compute(tree, ORG, limit=10)

    assert len(radius.affected) == 10
    assert radius.affected_count == 50
    assert radius.truncated


def test_an_unknown_node_reaches_nothing_rather_than_everything(tree: Hierarchy) -> None:
    """Failing closed: a typo must not report an organisation-wide blast radius."""
    radius = compute(tree, "team-that-does-not-exist")

    assert radius.is_local
    assert radius.affected == ()


def test_an_empty_tree_produces_an_empty_radius() -> None:
    assert compute(Hierarchy.of([]), None).is_local


def test_the_record_carries_the_count_as_well_as_the_list(tree: Hierarchy) -> None:
    record = compute(tree, DIVISION).to_record()

    assert record["affected_count"] == 3
    assert record["team_count"] == 2
    assert record["truncated"] is False


def test_an_unreadable_tree_reports_the_scope_as_unknown() -> None:
    """Unknown and "nothing beneath it" are different facts, and the second is
    the one a reviewer reads as reassurance."""
    radius = compute(None, PAYMENTS)

    assert not radius.known
    assert "unknown rather than small" in radius.describe()
    assert radius.to_record()["known"] is False
