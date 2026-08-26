"""Precedence, tie-breaking, least-permissive, and the explanation that comes with it."""

from __future__ import annotations

from datetime import timedelta

from platform.autonomy.levels import AutonomyLevel
from platform.autonomy.policy import PolicySet, override_expiring
from platform.autonomy.risk import RiskClass
from platform.autonomy.scopes import PolicyScope, ScopeKind
from tests.unit.platform.autonomy.conftest import NOON, action, rule, subject


def test_with_nothing_configured_every_action_resolves_to_propose_only() -> None:
    """The absence of a rule is the safe answer, never the permissive one."""
    from platform.autonomy.resolution import resolve

    for risk in RiskClass:
        resolved = resolve(action(risk=risk), PolicySet(), at=NOON)
        assert resolved.level is AutonomyLevel.PROPOSE_ONLY
        assert resolved.from_default
        assert "No rule covers" in resolved.reason


def test_the_most_specific_applicable_rule_wins() -> None:
    from platform.autonomy.resolution import resolve

    policies = PolicySet(
        rules=(
            rule(ScopeKind.DEPLOYMENT, AutonomyLevel.PROPOSE_ONLY),
            rule(ScopeKind.RESOURCE_KIND, AutonomyLevel.ACT_ON_LOW_RISK, resource_kind="container"),
            rule(ScopeKind.RESOURCE, AutonomyLevel.ACT_AND_REPORT, resource_id="ct-101"),
        )
    )
    resolved = resolve(action(), policies, at=NOON)
    assert resolved.level is AutonomyLevel.ACT_AND_REPORT
    assert resolved.winner == "resource:::ct-101::"


def test_the_resolution_names_every_rule_it_considered_and_the_one_that_won() -> None:
    from platform.autonomy.resolution import resolve

    policies = PolicySet(
        rules=(
            rule(ScopeKind.DEPLOYMENT, AutonomyLevel.ACT_ON_LOW_RISK),
            rule(ScopeKind.RESOURCE, AutonomyLevel.ACT_AND_REPORT, resource_id="ct-999"),
        )
    )
    resolved = resolve(action(), policies, at=NOON)

    assert {entry.rule_id for entry in resolved.considered} == {
        "deployment:::::",
        "resource:::ct-999::",
    }
    applied = [entry for entry in resolved.considered if entry.applied]
    assert [entry.rule_id for entry in applied] == ["deployment:::::"]
    assert [entry.rule_id for entry in resolved.considered if entry.won] == ["deployment:::::"]
    missed = next(entry for entry in resolved.considered if not entry.applied)
    assert missed.reason == "does not cover ct-101"


def test_two_rules_at_the_same_specificity_resolve_to_the_less_permissive() -> None:
    """Order in a merged document is an artefact; it must not grant autonomy."""
    from platform.autonomy.resolution import resolve

    permissive = rule(ScopeKind.LABELS, AutonomyLevel.ACT_AND_REPORT, labels={"env": "lab"})
    cautious = rule(ScopeKind.LABELS, AutonomyLevel.PROPOSE_ONLY, labels={"tier": "backup"})
    target = subject(labels={"env": "lab", "tier": "backup"})

    one_way = resolve(action(subjects=(target,)), PolicySet(rules=(permissive, cautious)), at=NOON)
    other_way = resolve(
        action(subjects=(target,)), PolicySet(rules=(cautious, permissive)), at=NOON
    )

    assert one_way.level is AutonomyLevel.PROPOSE_ONLY
    assert one_way.winner == other_way.winner


def test_an_action_across_resources_takes_the_least_permissive_of_them() -> None:
    from platform.autonomy.resolution import resolve

    policies = PolicySet(
        rules=(
            rule(ScopeKind.RESOURCE, AutonomyLevel.ACT_AND_REPORT, resource_id="ct-101"),
            rule(ScopeKind.RESOURCE, AutonomyLevel.ACT_ON_LOW_RISK, resource_id="ct-102"),
            rule(ScopeKind.RESOURCE, AutonomyLevel.PROPOSE_ONLY, resource_id="ct-103"),
        )
    )
    proposed = action(subjects=(subject("ct-101"), subject("ct-102"), subject("ct-103")))
    resolved = resolve(proposed, policies, at=NOON)

    assert resolved.level is AutonomyLevel.PROPOSE_ONLY
    assert dict(resolved.per_subject) == {
        "ct-101": AutonomyLevel.ACT_AND_REPORT,
        "ct-102": AutonomyLevel.ACT_ON_LOW_RISK,
        "ct-103": AutonomyLevel.PROPOSE_ONLY,
    }
    assert "least permissive of the 3 resources" in resolved.reason
    assert [entry.rule_id for entry in resolved.considered if entry.won] == ["resource:::ct-103::"]


def test_a_rule_matching_by_label_loses_to_one_matching_by_capability_and_resource() -> None:
    from platform.autonomy.resolution import resolve

    policies = PolicySet(
        rules=(
            rule(ScopeKind.LABELS, AutonomyLevel.ACT_AND_REPORT, labels={"env": "lab"}),
            rule(
                ScopeKind.CAPABILITY_RESOURCE,
                AutonomyLevel.PROPOSE_ONLY,
                capability="restart_workload",
                resource_id="ct-101",
            ),
        )
    )
    resolved = resolve(action(subjects=(subject(labels={"env": "lab"}),)), policies, at=NOON)
    assert resolved.level is AutonomyLevel.PROPOSE_ONLY


def test_every_scope_kind_can_carry_a_level_and_be_the_one_that_applies() -> None:
    """Seven places a level may be set, each proven to reach a resolution."""
    from platform.autonomy.resolution import resolve

    target = subject("ct-101", kind="container", labels={"env": "lab"}, team="platform")
    proposed = action(subjects=(target,))
    scoped = {
        ScopeKind.DEPLOYMENT: {},
        ScopeKind.TEAM: {"team_node_id": "platform"},
        ScopeKind.RESOURCE_KIND: {"resource_kind": "container"},
        ScopeKind.LABELS: {"labels": {"env": "lab"}},
        ScopeKind.CAPABILITY: {"capability": "restart_workload"},
        ScopeKind.RESOURCE: {"resource_id": "ct-101"},
        ScopeKind.CAPABILITY_RESOURCE: {
            "capability": "restart_workload",
            "resource_id": "ct-101",
        },
    }
    assert set(scoped) == set(ScopeKind)

    for kind, fields in scoped.items():
        policies = PolicySet(rules=(rule(kind, AutonomyLevel.ACT_AND_REPORT, **fields),))
        resolved = resolve(proposed, policies, at=NOON)
        assert resolved.level is AutonomyLevel.ACT_AND_REPORT, kind
        assert not resolved.from_default, kind


def test_a_policy_referencing_a_resource_that_no_longer_exists_simply_does_not_apply() -> None:
    from platform.autonomy.resolution import resolve

    policies = PolicySet(
        rules=(rule(ScopeKind.RESOURCE, AutonomyLevel.ACT_AND_REPORT, resource_id="ct-gone"),)
    )
    resolved = resolve(action(), policies, at=NOON)
    assert resolved.level is AutonomyLevel.PROPOSE_ONLY
    assert [entry.applied for entry in resolved.considered] == [False]


def test_an_override_raises_autonomy_until_it_expires_and_not_after() -> None:
    from platform.autonomy.resolution import resolve

    override = override_expiring(
        name="maintenance",
        scope=PolicyScope(kind=ScopeKind.TEAM, team_node_id="platform"),
        level=AutonomyLevel.ACT_AND_REPORT,
        granted_at=NOON,
        seconds=7200,
        granted_by="ada",
    )
    policies = PolicySet(overrides=(override,))

    during = resolve(action(), policies, at=NOON + timedelta(hours=1))
    after = resolve(action(), policies, at=NOON + timedelta(hours=3))

    assert during.level is AutonomyLevel.ACT_AND_REPORT
    assert after.level is AutonomyLevel.PROPOSE_ONLY
    assert policies.expired(NOON + timedelta(hours=3)) == (override,)
    assert policies.expired(NOON + timedelta(hours=1)) == ()


def test_a_dry_run_rule_marks_the_resolution_without_changing_the_level() -> None:
    from platform.autonomy.resolution import resolve

    policies = PolicySet(
        rules=(rule(ScopeKind.DEPLOYMENT, AutonomyLevel.ACT_AND_REPORT, dry_run=True),)
    )
    resolved = resolve(action(), policies, at=NOON)
    assert resolved.level is AutonomyLevel.ACT_AND_REPORT
    assert resolved.dry_run
    assert "simulated" in resolved.reason


def test_resolution_is_pure_in_its_inputs() -> None:
    """Same action, same policies, same clock, same answer — asserted, not assumed."""
    from platform.autonomy.resolution import resolve

    policies = PolicySet(rules=(rule(ScopeKind.DEPLOYMENT, AutonomyLevel.ACT_ON_LOW_RISK),))
    proposed = action()
    first = resolve(proposed, policies, at=NOON)
    second = resolve(proposed, policies, at=NOON)
    assert first == second


def test_the_reason_written_for_a_person_spells_the_level_as_a_person_would() -> None:
    """The value belongs in a config file and an audit field, not mid-sentence.

    The resolution reason's own docstring says it explains the resolution *to a
    person*, and it was printing "so it resolves to propose_only:" — the
    deployment's own spelling, dropped verbatim into English. The console showed
    that sentence under every class of action on the autonomy screen, four times
    over.
    """
    assert AutonomyLevel.PROPOSE_ONLY.label == "propose-only"
    assert AutonomyLevel.ACT_ON_LOW_RISK.label == "act-on-low-risk"
    # The value is untouched: it is what a rule is written against and what an
    # audit row is compared by, and neither of those wants a prettier word.
    assert AutonomyLevel.PROPOSE_ONLY.value == "propose_only"
