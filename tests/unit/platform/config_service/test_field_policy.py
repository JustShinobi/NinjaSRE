"""Locked, required, approval-gated, allowed, and capped — enforced at the write.

``test_locks.py`` covers the structural half: merging skips a locked override
however it reached storage. This file covers the half an operator meets, where
a refusal has to name the field *and* the node that locked it, because a
constraint whose origin is invisible is one people route around rather than
argue with.
"""

from __future__ import annotations

import pytest

from platform.config_service.errors import FieldLocked, LockConflict
from platform.config_service.field_policy import (
    FieldPolicy,
    PolicySet,
    changed_paths,
    check_lock_addition,
    check_locks,
    constraint_errors,
    gated_paths,
    merged_along,
    missing_required,
)

pytestmark = pytest.mark.unit


# --- T018 / SC-002: lock enforcement on write --------------------------------


def test_writing_a_locked_field_is_refused_naming_the_field_and_the_node() -> None:
    with pytest.raises(FieldLocked) as raised:
        check_locks(
            "team", {"policies": {"masking": {"level": "off"}}}, {"policies.masking": "org"}
        )

    assert raised.value.path == "policies.masking.level"
    assert raised.value.locking_node_id == "org"
    assert "org" in str(raised.value)
    assert "team" in str(raised.value)


def test_writing_an_unlocked_field_beside_a_locked_one_is_allowed() -> None:
    check_locks("team", {"budget": 4}, {"policies.masking": "org"})


def test_a_lock_on_a_prefix_of_a_name_does_not_refuse_the_write() -> None:
    check_locks("team", {"policies": {"masking": "off"}}, {"policies.mask": "org"})


def test_a_node_may_write_a_field_it_locked_itself() -> None:
    """A node that could not set the field it locks could not pin a value at all."""
    document_locks = merged_along([PolicySet.of([FieldPolicy("budget", locked=True)])])

    check_locks("org", {"budget": 8}, inherited_locks={}, own=document_locks)


# --- T022 / FR-009: adding a lock where a descendant already overrides -------


def test_adding_a_lock_over_an_existing_override_is_refused_naming_the_descendants() -> None:
    with pytest.raises(LockConflict) as raised:
        check_lock_addition(
            "policies.masking.level",
            "org",
            {
                "team-payments": {"policies": {"masking": {"level": "off"}}},
                "team-search": {"policies": {"masking": {"level": "off"}}},
                "team-quiet": {"budget": 4},
            },
        )

    assert raised.value.overriding == ("team-payments", "team-search")
    assert "team-quiet" not in str(raised.value)


def test_adding_a_lock_nobody_overrides_is_allowed() -> None:
    check_lock_addition("policies.masking.level", "org", {"team": {"budget": 4}})


def test_locking_a_subtree_conflicts_with_an_override_beneath_it() -> None:
    with pytest.raises(LockConflict):
        check_lock_addition(
            "policies.masking", "org", {"team": {"policies": {"masking": {"level": "off"}}}}
        )


# --- T019 / FR-006: required fields ------------------------------------------


def test_a_required_field_with_no_value_anywhere_fails_validation() -> None:
    policies = PolicySet.of([FieldPolicy("integrations.active", required=True)])

    assert missing_required({"budget": 4}, policies) == ("integrations.active",)


def test_a_required_field_supplied_by_an_ancestor_satisfies_the_requirement() -> None:
    policies = PolicySet.of([FieldPolicy("policies.masking.level", required=True)])

    assert missing_required({"policies": {"masking": {"level": "strict"}}}, policies) == ()


def test_an_explicit_null_does_not_satisfy_a_required_field() -> None:
    """Clearing a required field is the same omission written differently."""
    policies = PolicySet.of([FieldPolicy("site", required=True)])

    assert missing_required({"site": None}, policies) == ("site",)


def test_an_empty_string_does_not_satisfy_a_required_field() -> None:
    policies = PolicySet.of([FieldPolicy("site", required=True)])

    assert missing_required({"site": ""}, policies) == ("site",)


def test_a_required_field_set_to_a_falsey_number_is_satisfied() -> None:
    """Zero is a value somebody chose."""
    policies = PolicySet.of([FieldPolicy("budget", required=True)])

    assert missing_required({"budget": 0}, policies) == ()


# --- T021 / FR-008: allowed values and ceilings ------------------------------


def test_a_value_outside_the_allowed_set_is_reported() -> None:
    policies = PolicySet.of(
        [FieldPolicy("models.investigator.model", allowed_values=("sonnet", "haiku"))]
    )

    errors = constraint_errors({"models": {"investigator": {"model": "opus"}}}, policies)

    assert [error.path for error in errors] == ["models.investigator.model"]
    assert "sonnet" in errors[0].message


def test_a_value_inside_the_allowed_set_passes() -> None:
    policies = PolicySet.of([FieldPolicy("level", allowed_values=("strict", "off"))])

    assert constraint_errors({"level": "strict"}, policies) == ()


def test_a_number_above_its_ceiling_is_reported() -> None:
    policies = PolicySet.of([FieldPolicy("agents.tool_budget", max_value=8)])

    errors = constraint_errors({"agents": {"tool_budget": 20}}, policies)

    assert [error.path for error in errors] == ["agents.tool_budget"]


def test_a_number_at_its_ceiling_passes() -> None:
    policies = PolicySet.of([FieldPolicy("agents.tool_budget", max_value=8)])

    assert constraint_errors({"agents": {"tool_budget": 8}}, policies) == ()


def test_a_ceiling_on_a_value_that_is_not_a_number_is_reported() -> None:
    policies = PolicySet.of([FieldPolicy("budget", max_value=8)])

    errors = constraint_errors({"budget": "lots"}, policies)

    assert [error.path for error in errors] == ["budget"]


def test_a_list_longer_than_its_cap_is_reported() -> None:
    policies = PolicySet.of([FieldPolicy("capabilities.enabled", max_items=2)])

    errors = constraint_errors({"capabilities": {"enabled": ["a", "b", "c"]}}, policies)

    assert [error.path for error in errors] == ["capabilities.enabled"]


def test_an_unset_field_violates_no_constraint() -> None:
    policies = PolicySet.of([FieldPolicy("budget", max_value=8, allowed_values=(1,))])

    assert constraint_errors({}, policies) == ()


# --- T020 / FR-007: approval-gated fields ------------------------------------


def test_a_change_to_a_gated_field_is_reported_as_needing_approval() -> None:
    policies = PolicySet.of([FieldPolicy("agents.prompts", approval_gated=True)])
    changed = changed_paths(
        {"agents": {"prompts": {"investigator": "old"}}, "budget": 4},
        {"agents": {"prompts": {"investigator": "new"}}, "budget": 8},
    )

    assert set(changed) == {"agents.prompts.investigator", "budget"}
    assert gated_paths(changed, policies) == ("agents.prompts.investigator",)


def test_an_unchanged_gated_field_needs_no_approval() -> None:
    policies = PolicySet.of([FieldPolicy("agents.prompts", approval_gated=True)])
    changed = changed_paths(
        {"agents": {"prompts": {"a": "x"}}}, {"agents": {"prompts": {"a": "x"}}}
    )

    assert gated_paths(changed, policies) == ()


def test_removing_a_gated_field_is_a_change_that_needs_approval() -> None:
    policies = PolicySet.of([FieldPolicy("agents.prompts", approval_gated=True)])
    changed = changed_paths({"agents": {"prompts": {"a": "x"}}}, {})

    assert gated_paths(changed, policies) == ("agents.prompts.a",)


def test_adding_a_gated_field_is_a_change_that_needs_approval() -> None:
    policies = PolicySet.of([FieldPolicy("policies.masking", approval_gated=True)])
    changed = changed_paths({}, {"policies": {"masking": {"level": "off"}}})

    assert gated_paths(changed, policies) == ("policies.masking.level",)


# --- Policies accumulate down the tree and never weaken ----------------------


def test_a_descendant_may_tighten_a_ceiling_but_not_raise_it() -> None:
    accumulated = merged_along(
        [
            PolicySet.of([FieldPolicy("budget", max_value=8)]),
            PolicySet.of([FieldPolicy("budget", max_value=4)]),
            PolicySet.of([FieldPolicy("budget", max_value=99)]),
        ]
    )

    policy = accumulated.for_path("budget")
    assert policy is not None
    assert policy.max_value == 4


def test_a_descendant_cannot_unlock_what_an_ancestor_locked() -> None:
    accumulated = merged_along(
        [
            PolicySet.of([FieldPolicy("masking", locked=True)]),
            PolicySet.of([FieldPolicy("masking", locked=False, required=True)]),
        ]
    )

    policy = accumulated.for_path("masking")
    assert policy is not None
    assert policy.locked
    assert policy.required


def test_allowed_value_sets_intersect_down_the_tree() -> None:
    accumulated = merged_along(
        [
            PolicySet.of([FieldPolicy("model", allowed_values=("a", "b", "c"))]),
            PolicySet.of([FieldPolicy("model", allowed_values=("b", "c", "d"))]),
        ]
    )

    policy = accumulated.for_path("model")
    assert policy is not None
    assert policy.allowed_values == ("b", "c")


# --- Round-tripping through storage ------------------------------------------


def test_a_policy_set_survives_a_round_trip_through_its_stored_records() -> None:
    original = PolicySet.of(
        [
            FieldPolicy("a", locked=True),
            FieldPolicy("b", required=True, allowed_values=("x",), max_value=3.0, max_items=2),
        ]
    )

    assert PolicySet.of_records(original.to_records()) == original


def test_a_policy_that_says_nothing_is_not_stored() -> None:
    assert len(PolicySet.of([FieldPolicy("a")])) == 0


def test_a_malformed_stored_record_is_skipped_rather_than_failing_the_read() -> None:
    """Refusing to resolve a hierarchy is refusing to investigate an incident."""
    assert len(PolicySet.of_records([{"path": ""}, "nonsense", {"path": "a", "locked": True}])) == 1
