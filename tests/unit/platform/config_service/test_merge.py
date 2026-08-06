"""The merge goldens. These pin the semantics every other test assumes.

Deep merge is the whole configuration service in one function: get it wrong and
a team silently inherits a value nobody set, or silently loses one somebody did.
So the cases are enumerated rather than sampled — dict recursion, list
replacement, scalar replacement, type mismatch in both directions, explicit
null, and a four-level chain — and each one states the answer rather than
computing it.
"""

from __future__ import annotations

import pytest

from platform.config_service.errors import ConfigTooDeep
from platform.config_service.merge import Layer, deep_merge, merge_layers

pytestmark = pytest.mark.unit


# --- deep_merge, the pure two-argument form ----------------------------------


def test_nested_dicts_merge_recursively() -> None:
    base = {"policies": {"masking": {"level": "strict", "patterns": ["a"]}, "memory": {}}}
    override = {"policies": {"masking": {"level": "off"}}}

    assert deep_merge(base, override) == {
        "policies": {"masking": {"level": "off", "patterns": ["a"]}, "memory": {}}
    }


def test_lists_replace_entirely_rather_than_concatenating() -> None:
    base = {"capabilities": {"disabled": ["kubectl-delete", "aws-terminate"]}}
    override = {"capabilities": {"disabled": ["kubectl-drain"]}}

    assert deep_merge(base, override) == {"capabilities": {"disabled": ["kubectl-drain"]}}


def test_scalars_replace() -> None:
    assert deep_merge({"budget": 8}, {"budget": 3}) == {"budget": 3}


def test_a_key_absent_from_the_base_is_taken_from_the_override() -> None:
    assert deep_merge({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}


def test_a_key_absent_from_the_override_survives() -> None:
    assert deep_merge({"a": 1}, {"b": 2})["a"] == 1


def test_a_dict_replaces_a_scalar() -> None:
    assert deep_merge({"model": "sonnet"}, {"model": {"provider": "ollama"}}) == {
        "model": {"provider": "ollama"}
    }


def test_a_scalar_replaces_a_dict() -> None:
    assert deep_merge({"model": {"provider": "ollama"}}, {"model": "sonnet"}) == {"model": "sonnet"}


def test_an_explicit_null_replaces_rather_than_being_ignored() -> None:
    """A null is a value. Treating it as absence makes a field unclearable."""
    assert deep_merge({"site": "eu1"}, {"site": None}) == {"site": None}


def test_the_inputs_are_not_mutated() -> None:
    base = {"policies": {"masking": {"level": "strict"}}}
    override = {"policies": {"masking": {"level": "off"}}}

    deep_merge(base, override)

    assert base == {"policies": {"masking": {"level": "strict"}}}
    assert override == {"policies": {"masking": {"level": "off"}}}


def test_a_control_key_is_data_like_any_other() -> None:
    """FR-003: no directive is interpreted, so ``_append`` is just a field name."""
    merged = deep_merge({"tags": ["a"]}, {"_append": {"tags": ["b"]}})

    assert merged == {"tags": ["a"], "_append": {"tags": ["b"]}}


def test_a_configuration_nested_past_the_bound_is_refused() -> None:
    deep: dict[str, object] = {}
    cursor = deep
    for _ in range(40):
        nested: dict[str, object] = {}
        cursor["down"] = nested
        cursor = nested

    with pytest.raises(ConfigTooDeep):
        deep_merge({}, deep)


# --- merge_layers, the root-to-leaf form -------------------------------------


def test_a_four_level_chain_merges_root_to_leaf() -> None:
    """SC-001. Each level overrides its ancestors and nothing else."""
    result = merge_layers(
        [
            Layer("org", {"models": {"investigator": "opus"}, "budget": 8, "region": "eu"}),
            Layer("division", {"models": {"intake": "haiku"}, "budget": 12}),
            Layer("team", {"models": {"investigator": "sonnet"}}),
            Layer("squad", {"budget": 4}),
        ]
    )

    assert result.values == {
        "models": {"investigator": "sonnet", "intake": "haiku"},
        "budget": 4,
        "region": "eu",
    }


def test_every_merged_value_names_the_node_that_supplied_it() -> None:
    """SC-005."""
    result = merge_layers(
        [
            Layer("org", {"models": {"investigator": "opus"}, "budget": 8, "region": "eu"}),
            Layer("division", {"models": {"intake": "haiku"}, "budget": 12}),
            Layer("team", {"models": {"investigator": "sonnet"}}),
            Layer("squad", {"budget": 4}),
        ]
    )

    assert result.provenance == {
        "models.investigator": "team",
        "models.intake": "division",
        "budget": "squad",
        "region": "org",
    }
    assert result.source_of("models.investigator") == "team"


def test_provenance_follows_a_replaced_subtree() -> None:
    """A scalar replacing a dict takes the provenance of everything beneath it."""
    result = merge_layers(
        [
            Layer("org", {"masking": {"level": "strict", "patterns": ["a"]}}),
            Layer("team", {"masking": "off"}),
        ]
    )

    assert result.values == {"masking": "off"}
    assert result.provenance == {"masking": "team"}


def test_an_empty_mapping_still_names_its_source() -> None:
    result = merge_layers([Layer("org", {"surfaces": {}})])

    assert result.provenance == {"surfaces": "org"}


def test_a_single_layer_is_its_own_effective_configuration() -> None:
    result = merge_layers([Layer("org", {"budget": 8})])

    assert result.values == {"budget": 8}
    assert result.provenance == {"budget": "org"}


def test_no_layers_merges_to_nothing() -> None:
    result = merge_layers([])

    assert result.values == {}
    assert result.provenance == {}


def test_the_same_layers_always_merge_to_the_same_result() -> None:
    """FR-003: deterministic, so a cached resolution and a fresh one agree."""
    layers = [
        Layer("org", {"a": {"b": 1, "c": 2}, "d": [1, 2]}),
        Layer("team", {"a": {"c": 3}, "d": [3]}),
    ]

    first = merge_layers(layers)
    second = merge_layers(layers)

    assert first.values == second.values
    assert first.provenance == second.provenance
