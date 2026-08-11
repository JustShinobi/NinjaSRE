"""The per-class reading: one sentence each, in the deployment's own words."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from config.constants.autonomy import REPRESENTATIVE_ACTIONS, RISK_CLASSES
from platform.autonomy.decision import AutonomyGate, Outcome
from platform.autonomy.levels import AutonomyLevel
from platform.autonomy.outlook import outlook_of, representative_actions
from platform.autonomy.policy import PolicyRule, PolicySet
from platform.autonomy.risk import RiskClass
from platform.autonomy.scopes import PolicyScope, ScopeKind
from platform.estate.kinds import core_registry

AT = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def _at() -> datetime:
    """Return a fixed instant, so two runs of this file agree."""
    return AT


async def _outlook(policies: PolicySet) -> tuple[str, ...]:
    """Return the outcome of each risk class under ``policies``."""
    gate = AutonomyGate(policies=policies, clock=_at)
    decisions = tuple(
        [await gate.decide(action) for action in representative_actions(team_node_id="payments")]
    )
    return tuple(entry.outcome for entry in outlook_of(decisions))


def test_there_is_exactly_one_representative_action_per_risk_class() -> None:
    assert [entry.risk_class for entry in REPRESENTATIVE_ACTIONS] == list(RISK_CLASSES)


def test_every_representative_resource_kind_is_one_the_estate_models() -> None:
    # A kind nothing models is a kind no ``resource_kind`` rule can be written
    # against, so the reading would silently ignore the rules that exist.
    known = set(core_registry().names())
    for entry in REPRESENTATIVE_ACTIONS:
        assert entry.resource_kind in known, f"{entry.resource_kind!r} is not a modelled kind"


def test_no_representative_capability_borrows_a_real_tool_s_name() -> None:
    from capabilities.registry.discovery import discover

    installed = {tool.name for tool in discover().tools}
    for entry in REPRESENTATIVE_ACTIONS:
        assert entry.capability not in installed


async def test_a_deployment_that_configured_nothing_proposes_every_class() -> None:
    assert await _outlook(PolicySet()) == tuple([Outcome.PROPOSE.value] * len(RISK_CLASSES))


async def test_acting_on_low_risk_splits_the_classes_at_the_bound() -> None:
    policies = PolicySet(
        rules=(
            PolicyRule(
                scope=PolicyScope(kind=ScopeKind.DEPLOYMENT),
                level=AutonomyLevel.ACT_ON_LOW_RISK,
                risk_bound=RiskClass.LOW,
            ),
        )
    )
    # Trivial and low run unattended; everything above the bound waits.
    assert await _outlook(policies) == (
        Outcome.EXECUTE.value,
        Outcome.EXECUTE.value,
        Outcome.APPROVE.value,
        Outcome.APPROVE.value,
        Outcome.APPROVE.value,
    )


async def test_dry_run_simulates_what_would_otherwise_have_run() -> None:
    policies = PolicySet(
        rules=(
            PolicyRule(
                scope=PolicyScope(kind=ScopeKind.DEPLOYMENT),
                level=AutonomyLevel.ACT_AND_REPORT,
            ),
        ),
        dry_run=True,
    )
    assert await _outlook(policies) == tuple([Outcome.SIMULATE.value] * len(RISK_CLASSES))


async def test_each_sentence_names_the_class_and_says_what_would_happen() -> None:
    gate = AutonomyGate(policies=PolicySet(), clock=_at)
    decisions = tuple(
        [await gate.decide(action) for action in representative_actions(team_node_id="payments")]
    )
    readings = outlook_of(decisions)
    for reading in readings:
        sentence = reading.describe()
        assert reading.summary in sentence
        assert "would be proposed" in sentence


async def test_a_short_answer_is_refused_rather_than_rendered() -> None:
    gate = AutonomyGate(policies=PolicySet(), clock=_at)
    one = await gate.decide(representative_actions(team_node_id="payments")[0])
    with pytest.raises(ValueError, match="one decision per representative action"):
        outlook_of((one,))
