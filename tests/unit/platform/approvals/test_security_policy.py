"""The organisation's constraints: what they gate, what they refuse, and what
a change to them does to work already in the queue.

Two halves, and the second is the one that is easy to get wrong. Deciding what
needs approval is straightforward. Deciding what a *policy change* means for the
changes already queued under the old policy is not, and the wrong answer —
silently reinterpreting pending state — is worse than asking for a re-review,
because nobody sees it happen.

The rule in three sentences: an approved change keeps its effect; a queued change
stays queued; each queued change is re-checked against the new policy when
somebody decides it. ``effect_of`` states that from the value rather than from a
document, so a console can show an operator what they are about to do.
"""

from __future__ import annotations

import pytest

from config.constants.security import (
    API_TOKEN_DEFAULT_LIFETIME_DAYS,
    PENDING_CHANGE_EXPIRY_HOURS,
    PENDING_CHANGE_MAX_EXPIRY_HOURS,
    SIDE_EFFECT_DESTRUCTIVE,
    SIDE_EFFECT_READ,
    SIDE_EFFECT_WRITE_IRREVERSIBLE,
)
from platform.approvals.errors import PolicyLocked, PolicyViolation
from platform.approvals.models import ChangeType
from platform.approvals.policy import (
    DEFAULT_POLICY,
    SecurityPolicy,
    TokenLifecycleDefaults,
)

pytestmark = pytest.mark.unit


# --- What is gated -----------------------------------------------------------


def test_nothing_is_gated_by_default() -> None:
    """A fresh deployment's first change must not sit in a queue with no reviewer."""
    assert not any(DEFAULT_POLICY.requires_approval(kind) for kind in ChangeType)


def test_self_approval_is_forbidden_by_default() -> None:
    """The one default that is strict, because the two-person case is the point."""
    assert not DEFAULT_POLICY.permits_self_approval()


def test_a_policy_gates_the_change_types_it_names() -> None:
    policy = SecurityPolicy(
        require_approval_for=frozenset({ChangeType.PROMPT, ChangeType.CAPABILITY})
    )

    assert policy.requires_approval(ChangeType.PROMPT)
    assert policy.requires_approval(ChangeType.CAPABILITY)
    assert not policy.requires_approval(ChangeType.CONFIGURATION)


def test_side_effect_levels_are_gated_by_name_not_by_rank() -> None:
    """A control that silently widens when somebody adds an enum member is not one."""
    policy = SecurityPolicy(
        require_approval_for_side_effect_levels=(SIDE_EFFECT_WRITE_IRREVERSIBLE,)
    )

    assert policy.requires_approval_for_level(SIDE_EFFECT_WRITE_IRREVERSIBLE)
    assert not policy.requires_approval_for_level(SIDE_EFFECT_DESTRUCTIVE)
    assert not policy.requires_approval_for_level(SIDE_EFFECT_READ)


def test_an_unknown_side_effect_level_is_refused_at_construction() -> None:
    with pytest.raises(ValueError, match="No side-effect level"):
        SecurityPolicy(require_approval_for_side_effect_levels=("write_maybe",))


# --- What is refused ---------------------------------------------------------


def test_a_value_under_the_ceiling_is_allowed() -> None:
    SecurityPolicy(max_values={"budgets.iterations": 10}).check_settings(
        {"budgets": {"iterations": 10}}
    )


def test_a_value_over_the_ceiling_names_the_path_and_both_numbers() -> None:
    policy = SecurityPolicy(max_values={"budgets.iterations": 10})

    with pytest.raises(PolicyViolation) as raised:
        policy.check_settings({"budgets": {"iterations": 25}})

    assert "budgets.iterations" in str(raised.value)
    assert "10" in str(raised.value)
    assert "25" in str(raised.value)


def test_a_non_numeric_value_under_a_ceiling_is_refused() -> None:
    """A ceiling on a string is a mistake worth reporting, not one to ignore."""
    with pytest.raises(PolicyViolation, match="not a number"):
        SecurityPolicy(max_values={"budgets.iterations": 10}).check_settings(
            {"budgets": {"iterations": "lots"}}
        )


def test_a_locked_setting_names_the_policy_rather_than_a_node() -> None:
    """There is no node above the organisation's policy to argue with."""
    with pytest.raises(PolicyLocked, match="security policy"):
        SecurityPolicy(locked_settings=("policies.masking",)).check_settings(
            {"policies": {"masking": {"level": "off"}}}
        )


def test_a_lock_does_not_reach_a_field_whose_name_it_prefixes() -> None:
    SecurityPolicy(locked_settings=("policies.mask",)).check_settings(
        {"policies": {"masking": {"level": "off"}}}
    )


def test_a_required_setting_cannot_be_cleared() -> None:
    with pytest.raises(PolicyViolation, match="required"):
        SecurityPolicy(required_settings=("policies.masking.level",)).check_settings(
            {"policies": {"masking": {"level": ""}}}
        )


def test_a_patch_that_does_not_mention_a_required_setting_is_left_alone() -> None:
    """Otherwise every partial write would have to carry every required value."""
    SecurityPolicy(required_settings=("policies.masking.level",)).check_settings(
        {"budgets": {"iterations": 4}}
    )


def test_zero_and_false_are_values_somebody_chose() -> None:
    policy = SecurityPolicy(required_settings=("budgets.iterations", "policies.masking.enabled"))

    policy.check_settings({"budgets": {"iterations": 0}})
    policy.check_settings({"policies": {"masking": {"enabled": False}}})


def test_an_allowed_value_set_is_closed() -> None:
    policy = SecurityPolicy(allowed_values={"policies.masking.level": ("standard", "strict")})

    policy.check_settings({"policies": {"masking": {"level": "strict"}}})
    with pytest.raises(PolicyViolation, match="must be one of"):
        policy.check_settings({"policies": {"masking": {"level": "off"}}})


def test_every_violation_is_reported_rather_than_the_first() -> None:
    """An operator fixing one field per submission stops using the form."""
    policy = SecurityPolicy(
        max_values={"budgets.iterations": 10, "budgets.tools": 5},
        allowed_values={"policies.masking.level": ("strict",)},
    )

    with pytest.raises(PolicyViolation) as raised:
        policy.check_settings(
            {
                "budgets": {"iterations": 25, "tools": 9},
                "policies": {"masking": {"level": "off"}},
            }
        )

    assert len(raised.value.violations) == 3


# --- Token lifecycle ------------------------------------------------


def test_token_defaults_come_from_the_platform_when_the_policy_says_nothing() -> None:
    assert DEFAULT_POLICY.token_defaults().expiry_days == API_TOKEN_DEFAULT_LIFETIME_DAYS


def test_a_policy_sets_the_token_lifecycle_the_identity_layer_applies() -> None:
    policy = SecurityPolicy(
        tokens=TokenLifecycleDefaults(expiry_days=30, warn_before_days=7, revoke_inactive_days=14)
    )

    assert policy.token_defaults().expiry_days == 30
    assert policy.token_defaults().revoke_inactive_days == 14


def test_a_warning_that_arrives_before_the_token_exists_is_refused() -> None:
    with pytest.raises(ValueError, match="arrives before the token exists"):
        TokenLifecycleDefaults(expiry_days=7, warn_before_days=14)


# --- Change expiry -----------------------------------------------------------


def test_the_default_expiry_is_the_platform_default() -> None:
    assert DEFAULT_POLICY.change_expiry_hours == PENDING_CHANGE_EXPIRY_HOURS


def test_an_expiry_beyond_the_ceiling_is_refused() -> None:
    with pytest.raises(ValueError, match="may wait between"):
        SecurityPolicy(change_expiry_hours=PENDING_CHANGE_MAX_EXPIRY_HOURS + 1)


def test_an_expiry_of_nothing_is_refused() -> None:
    with pytest.raises(ValueError, match="may wait between"):
        SecurityPolicy(change_expiry_hours=0)


# --- Changing the policy --------------------------------------------


def test_an_unchanged_policy_affects_nothing() -> None:
    effect = DEFAULT_POLICY.effect_of(SecurityPolicy())

    assert effect.is_noop
    assert "affects nothing" in effect.describe()


def test_newly_gating_a_change_type_is_reported() -> None:
    effect = DEFAULT_POLICY.effect_of(
        SecurityPolicy(require_approval_for=frozenset({ChangeType.PROMPT}))
    )

    assert effect.newly_gated == (ChangeType.PROMPT,)
    assert "Prompt changes will need approval" in effect.describe()


def test_no_longer_gating_a_change_type_is_reported() -> None:
    before = SecurityPolicy(require_approval_for=frozenset({ChangeType.PROMPT}))

    effect = before.effect_of(SecurityPolicy())

    assert effect.no_longer_gated == (ChangeType.PROMPT,)


def test_a_tightened_ceiling_is_reported_as_tightened() -> None:
    before = SecurityPolicy(max_values={"budgets.iterations": 20})

    effect = before.effect_of(SecurityPolicy(max_values={"budgets.iterations": 10}))

    assert effect.tightened_settings == ("budgets.iterations",)
    assert effect.relaxed_settings == ()


def test_a_relaxed_ceiling_is_reported_as_relaxed() -> None:
    before = SecurityPolicy(max_values={"budgets.iterations": 10})

    effect = before.effect_of(SecurityPolicy(max_values={"budgets.iterations": 20}))

    assert effect.relaxed_settings == ("budgets.iterations",)


def test_a_policy_change_never_applies_or_discards_queued_work() -> None:
    """Stated from the value rather than from a paragraph nobody reads."""
    effect = DEFAULT_POLICY.effect_of(
        SecurityPolicy(
            require_approval_for=frozenset({ChangeType.PROMPT}),
            max_values={"budgets.iterations": 1},
        )
    )

    assert effect.applied_automatically == ()
    assert effect.discarded_automatically == ()
    assert "already approved keep their effect" in effect.describe()
    assert "stay queued" in effect.describe()


# --- Storage -----------------------------------------------------------------


def test_a_policy_round_trips_through_its_stored_form() -> None:
    policy = SecurityPolicy(
        require_approval_for=frozenset({ChangeType.PROMPT, ChangeType.REMEDIATION}),
        require_approval_for_side_effect_levels=(SIDE_EFFECT_DESTRUCTIVE,),
        allow_self_approval=True,
        locked_settings=("policies.masking",),
        max_values={"budgets.iterations": 10.0},
        required_settings=("policies.masking.level",),
        allowed_values={"policies.masking.level": ("standard", "strict")},
        tokens=TokenLifecycleDefaults(expiry_days=30, warn_before_days=7, revoke_inactive_days=14),
        change_expiry_hours=48.0,
        log_all_changes=False,
    )

    assert SecurityPolicy.of_record(policy.to_record()) == policy


def test_an_empty_record_reads_back_as_the_default_policy() -> None:
    assert SecurityPolicy.of_record({}) == DEFAULT_POLICY
