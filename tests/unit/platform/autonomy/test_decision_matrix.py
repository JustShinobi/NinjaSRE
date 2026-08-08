"""Every level × every risk class × every scope, and what each combination decides.

Exhaustive rather than sampled. That is affordable exactly because the sets are
closed and resolution is pure: three levels, five risk classes, seven scope
kinds, and no clock or database anywhere in the calculation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from platform.autonomy.decision import AutonomyGate, Outcome
from platform.autonomy.levels import AutonomyLevel
from platform.autonomy.policy import PolicySet
from platform.autonomy.risk import RiskClass
from platform.autonomy.scopes import ScopeKind
from platform.autonomy.subjects import ProposedAction
from tests.unit.platform.autonomy.conftest import NOON, action, rule, subject

#: The fields that make each scope kind name the one resource the matrix uses.
SCOPE_FIELDS: dict[ScopeKind, dict[str, Any]] = {
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


@dataclass(slots=True)
class RecordingActuator:
    """An actuator that performs nothing and remembers being asked to."""

    calls: list[ProposedAction] = field(default_factory=list)

    async def perform(self, action: ProposedAction) -> str:
        """Record the call and return a result the gate can carry."""
        self.calls.append(action)
        return "performed"


def _matrix_action(risk: RiskClass) -> ProposedAction:
    """Return the one action every matrix row is decided about."""
    return action(subjects=(subject("ct-101", labels={"env": "lab"}),), risk=risk)


def expected(level: AutonomyLevel, risk: RiskClass) -> Outcome:
    """Return what the specification says this combination decides.

    Written as the rule rather than as a table of 105 answers, because a table
    copied from the implementation proves only that the implementation equals
    itself.
    """
    if level is AutonomyLevel.PROPOSE_ONLY:
        return Outcome.PROPOSE
    if level is AutonomyLevel.ACT_ON_LOW_RISK:
        return Outcome.EXECUTE if risk.at_or_below(RiskClass.LOW) else Outcome.APPROVE
    return Outcome.EXECUTE


@pytest.mark.parametrize("scope_kind", list(ScopeKind))
@pytest.mark.parametrize("risk", list(RiskClass))
@pytest.mark.parametrize("level", list(AutonomyLevel))
async def test_every_level_by_risk_class_by_scope_decides_what_the_specification_says(
    level: AutonomyLevel, risk: RiskClass, scope_kind: ScopeKind
) -> None:
    policies = PolicySet(
        rules=(rule(scope_kind, level, risk_bound=RiskClass.LOW, **SCOPE_FIELDS[scope_kind]),)
    )
    actuator = RecordingActuator()
    gate = AutonomyGate(policies=policies, clock=lambda: NOON)

    decision = await gate.run(_matrix_action(risk), actuator)

    assert decision.outcome is expected(level, risk)
    assert decision.executed is (decision.outcome is Outcome.EXECUTE)
    assert len(actuator.calls) == (1 if decision.outcome is Outcome.EXECUTE else 0)
    assert decision.resolution.level is level


@pytest.mark.parametrize("risk", list(RiskClass))
async def test_with_no_configuration_every_risk_class_needs_a_person(risk: RiskClass) -> None:
    """The default posture, asserted across the whole scale rather than once."""
    actuator = RecordingActuator()
    gate = AutonomyGate(clock=lambda: NOON)

    decision = await gate.run(_matrix_action(risk), actuator)

    assert decision.outcome is Outcome.PROPOSE
    assert decision.needs_human
    assert not decision.executed
    assert actuator.calls == []


@pytest.mark.parametrize("bound", list(RiskClass))
async def test_the_risk_bound_is_the_operators_definition_of_low(bound: RiskClass) -> None:
    """``act_on_low_risk`` draws the line where the rule says, not where we do."""
    actuator = RecordingActuator()
    for risk in RiskClass:
        policies = PolicySet(
            rules=(rule(ScopeKind.DEPLOYMENT, AutonomyLevel.ACT_ON_LOW_RISK, risk_bound=bound),)
        )
        gate = AutonomyGate(policies=policies, clock=lambda: NOON)
        decision = await gate.run(_matrix_action(risk), actuator)
        assert decision.outcome is (Outcome.EXECUTE if risk.at_or_below(bound) else Outcome.APPROVE)
