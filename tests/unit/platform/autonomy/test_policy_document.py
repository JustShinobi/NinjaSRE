"""Save-time validation, and the document a posture is reviewable as."""

from __future__ import annotations

from datetime import UTC, datetime, time
from typing import Any

import pytest

from platform.autonomy.bounds import BudgetRule, FreezeWindow
from platform.autonomy.errors import MalformedPolicy
from platform.autonomy.levels import AutonomyLevel
from platform.autonomy.policy import PolicyRule, PolicySet, TimedOverride, override_expiring
from platform.autonomy.risk import RiskClass
from platform.autonomy.scopes import PolicyScope, ScopeKind
from tests.unit.platform.autonomy.conftest import NOON


def a_full_policy_set() -> PolicySet:
    """Return a posture using every kind of entry a document can hold."""
    return PolicySet(
        dry_run=False,
        rules=(
            PolicyRule(
                scope=PolicyScope(kind=ScopeKind.DEPLOYMENT),
                level=AutonomyLevel.PROPOSE_ONLY,
            ),
            PolicyRule(
                scope=PolicyScope(kind=ScopeKind.CAPABILITY, capability="unlock_guest"),
                level=AutonomyLevel.ACT_AND_REPORT,
            ),
            PolicyRule(
                scope=PolicyScope(kind=ScopeKind.LABELS, labels={"env": "lab"}),
                level=AutonomyLevel.ACT_ON_LOW_RISK,
                risk_bound=RiskClass.MODERATE,
                dry_run=True,
            ),
        ),
        freezes=(
            FreezeWindow(
                name="backups",
                scope=PolicyScope(kind=ScopeKind.RESOURCE, resource_id="tank"),
                start=time(1, 0),
                end=time(4, 0),
                timezone="Europe/Lisbon",
                reason="backups run",
            ),
        ),
        budgets=(
            BudgetRule(
                name="hourly",
                counted_by="capability",
                limit=4,
                interval_seconds=1800.0,
                scope=PolicyScope(kind=ScopeKind.TEAM, team_node_id="platform"),
            ),
        ),
        overrides=(
            TimedOverride(
                name="maintenance",
                scope=PolicyScope(kind=ScopeKind.TEAM, team_node_id="platform"),
                level=AutonomyLevel.ACT_AND_REPORT,
                expires_at=datetime(2026, 3, 12, 14, 0, tzinfo=UTC),
                granted_by="ada",
                reason="rack move",
            ),
        ),
    )


def test_a_posture_survives_a_round_trip_through_its_document() -> None:
    """Export and import are the same shape, asserted rather than hoped for."""
    original = a_full_policy_set()
    assert PolicySet.of_document(original.to_document()) == original


def test_the_document_is_json_shaped_so_a_review_can_read_it() -> None:
    import json

    document = a_full_policy_set().to_document()
    assert json.loads(json.dumps(document)) == document


@pytest.mark.parametrize(
    ("document", "path", "detail"),
    [
        ({"rules": {"level": "act_and_report"}}, "rules", "must be a list"),
        ({"rules": ["act_and_report"]}, "rules[0]", "must be an object"),
        (
            {"rules": [{"scope": {"kind": "galaxy"}, "level": "act_and_report"}]},
            "rules[0].scope.kind",
            "not a scope kind",
        ),
        (
            {"rules": [{"scope": {"kind": "resource"}, "level": "act_and_report"}]},
            "rules[0].scope",
            "needs resource_id",
        ),
        (
            {"rules": [{"scope": {"kind": "deployment"}, "level": "run_wild"}]},
            "rules[0].level",
            "not an autonomy level",
        ),
        (
            {
                "rules": [
                    {
                        "scope": {"kind": "deployment"},
                        "level": "act_on_low_risk",
                        "risk_bound": "reckless",
                    }
                ]
            },
            "rules[0].risk_bound",
            "not a risk class",
        ),
        (
            {
                "freezes": [
                    {
                        "name": "backups",
                        "scope": {"kind": "deployment"},
                        "start": "1am",
                        "end": "04:00",
                    }
                ]
            },
            "freezes[0].start",
            "not a time of day",
        ),
        (
            {
                "freezes": [
                    {
                        "name": "backups",
                        "scope": {"kind": "deployment"},
                        "start": "01:00",
                        "end": "04:00",
                        "timezone": "Mars/Olympus",
                    }
                ]
            },
            "freezes[0]",
            "not a timezone",
        ),
        (
            {"budgets": [{"name": "hourly", "counted_by": "vibes"}]},
            "budgets[0]",
            "not something a budget counts against",
        ),
        (
            {"budgets": [{"name": "hourly", "limit": "lots"}]},
            "budgets[0].limit",
            "must be a whole number",
        ),
        (
            {
                "overrides": [
                    {
                        "name": "maintenance",
                        "scope": {"kind": "deployment"},
                        "level": "act_and_report",
                        "expires_at": "2026-03-12T14:00:00",
                    }
                ]
            },
            "overrides[0].expires_at",
            "names no timezone",
        ),
        ({"dry_run": "yes"}, "dry_run", "must be true or false"),
    ],
)
def test_a_malformed_policy_fails_at_save_time_naming_the_field(
    document: dict[str, Any], path: str, detail: str
) -> None:
    """Never at decision time. A refusal mid-incident about a typo is unusable."""
    with pytest.raises(MalformedPolicy) as rejected:
        PolicySet.of_document(document)
    assert rejected.value.path == path
    assert detail in rejected.value.reason


def test_an_empty_document_is_a_valid_posture_and_it_is_the_safe_one() -> None:
    from platform.autonomy.resolution import resolve
    from tests.unit.platform.autonomy.conftest import action

    policies = PolicySet.of_document({})
    assert policies == PolicySet()
    assert resolve(action(), policies, at=NOON).level is AutonomyLevel.PROPOSE_ONLY


def test_more_rules_than_the_ceiling_is_refused_rather_than_accepted_slowly() -> None:
    from config.constants.autonomy import MAX_AUTONOMY_RULES

    too_many = tuple(
        PolicyRule(
            scope=PolicyScope(kind=ScopeKind.RESOURCE, resource_id=f"ct-{index}"),
            level=AutonomyLevel.PROPOSE_ONLY,
        )
        for index in range(MAX_AUTONOMY_RULES + 1)
    )
    with pytest.raises(MalformedPolicy, match="may configure"):
        PolicySet(rules=too_many)


def test_an_override_longer_than_the_ceiling_is_a_policy_change_not_an_override() -> None:
    with pytest.raises(MalformedPolicy, match="hours at most"):
        override_expiring(
            name="forever",
            scope=PolicyScope(kind=ScopeKind.DEPLOYMENT),
            level=AutonomyLevel.ACT_AND_REPORT,
            granted_at=NOON,
            seconds=60 * 60 * 48,
        )


def test_a_scope_that_names_nothing_cannot_be_constructed() -> None:
    """A rule scoped to nobody is a rule scoped to everybody."""
    for kind, missing in (
        (ScopeKind.TEAM, "team_node_id"),
        (ScopeKind.RESOURCE_KIND, "resource_kind"),
        (ScopeKind.LABELS, "labels"),
        (ScopeKind.CAPABILITY, "capability"),
        (ScopeKind.RESOURCE, "resource_id"),
    ):
        with pytest.raises(ValueError, match=missing):
            PolicyScope(kind=kind)


def test_the_same_scope_written_twice_is_the_same_rule_identifier() -> None:
    """What makes a preview say "this rule changed" rather than "one went"."""
    one = PolicyScope(kind=ScopeKind.LABELS, labels={"env": "lab", "tier": "backup"})
    other = PolicyScope(kind=ScopeKind.LABELS, labels={"tier": "backup", "env": "lab"})
    assert one.identity == other.identity
