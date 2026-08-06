"""SC-002: a locked field is unoverridable by any descendant, at any depth.

The lock is enforced twice and this file covers the structural half. Merging
skips an override of a locked path, so a value that reached storage before the
lock existed — or by any route that bypassed the write check — still cannot take
effect. The write-time refusal, which is the half an operator actually meets,
is in ``test_field_policy.py``.
"""

from __future__ import annotations

import pytest

from platform.config_service.merge import Layer, merge_layers

pytestmark = pytest.mark.unit


def test_a_child_cannot_override_a_locked_field() -> None:
    result = merge_layers(
        [
            Layer(
                "org",
                {"policies": {"masking": {"level": "strict"}}},
                locked=("policies.masking.level",),
            ),
            Layer("team", {"policies": {"masking": {"level": "off"}}}),
        ]
    )

    assert result.values == {"policies": {"masking": {"level": "strict"}}}
    assert result.source_of("policies.masking.level") == "org"


@pytest.mark.parametrize("depth", [1, 2, 3, 4, 5])
def test_a_lock_holds_at_every_depth(depth: int) -> None:
    layers = [Layer("org", {"masking": "strict"}, locked=("masking",))]
    layers += [Layer(f"n{i}", {"masking": "off"}) for i in range(depth)]

    result = merge_layers(layers)

    assert result.values == {"masking": "strict"}
    assert result.source_of("masking") == "org"


def test_locking_a_subtree_locks_everything_beneath_it() -> None:
    """A lock on ``policies.masking`` covers ``policies.masking.level``."""
    result = merge_layers(
        [
            Layer(
                "org",
                {"policies": {"masking": {"level": "strict", "patterns": []}}},
                locked=("policies.masking",),
            ),
            Layer("team", {"policies": {"masking": {"level": "off", "patterns": ["x"]}}}),
        ]
    )

    assert result.values == {"policies": {"masking": {"level": "strict", "patterns": []}}}


def test_a_lock_does_not_reach_a_sibling_field() -> None:
    result = merge_layers(
        [
            Layer("org", {"masking": "strict", "budget": 8}, locked=("masking",)),
            Layer("team", {"masking": "off", "budget": 4}),
        ]
    )

    assert result.values == {"masking": "strict", "budget": 4}


def test_a_lock_does_not_reach_a_field_whose_name_it_prefixes() -> None:
    """``policies.mask`` must not lock ``policies.masking``."""
    result = merge_layers(
        [
            Layer("org", {"policies": {"mask": 1, "masking": "strict"}}, locked=("policies.mask",)),
            Layer("team", {"policies": {"mask": 2, "masking": "off"}}),
        ]
    )

    assert result.values == {"policies": {"mask": 1, "masking": "off"}}


def test_a_descendant_may_add_a_field_beneath_a_locked_one_it_did_not_lock() -> None:
    result = merge_layers(
        [
            Layer(
                "org",
                {"policies": {"masking": {"level": "strict"}}},
                locked=("policies.masking.level",),
            ),
            Layer("team", {"policies": {"masking": {"patterns": ["ticket"]}}}),
        ]
    )

    assert result.values == {"policies": {"masking": {"level": "strict", "patterns": ["ticket"]}}}


def test_a_descendant_may_lock_a_field_for_its_own_descendants() -> None:
    result = merge_layers(
        [
            Layer("org", {"budget": 8}),
            Layer("team", {"budget": 4}, locked=("budget",)),
            Layer("squad", {"budget": 1}),
        ]
    )

    assert result.values == {"budget": 4}
    assert result.source_of("budget") == "team"


def test_the_locking_node_is_reported_alongside_the_result() -> None:
    """An unexplained constraint is the one operators route around."""
    result = merge_layers(
        [
            Layer("org", {"masking": "strict"}, locked=("masking",)),
            Layer("team", {"masking": "off"}),
        ]
    )

    assert result.locks == {"masking": "org"}
    assert result.locked_by("masking") == "org"
    assert result.locked_by("budget") is None


def test_a_node_may_lock_a_field_it_does_not_itself_set() -> None:
    """Locking a default is how a platform team pins the shipped value."""
    result = merge_layers(
        [
            Layer("org", {}, locked=("policies.masking.level",)),
            Layer("team", {"policies": {"masking": {"level": "off"}}}),
        ]
    )

    assert result.values == {}
    assert result.locks == {"policies.masking.level": "org"}
