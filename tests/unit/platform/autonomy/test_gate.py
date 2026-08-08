"""The single path: what runs, what does not, and what the record says either way."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from typing import Any

import pytest

from platform.autonomy.audit import DecisionAuditor
from platform.autonomy.bounds import Bound, BudgetRule, FreezeWindow
from platform.autonomy.budget import InMemorySpendLedger
from platform.autonomy.decision import AutonomyGate, Outcome
from platform.autonomy.levels import AutonomyLevel
from platform.autonomy.policy import PolicySet, override_expiring
from platform.autonomy.risk import RiskClass
from platform.autonomy.scopes import PolicyScope, ScopeKind
from platform.autonomy.subjects import ProposedAction
from platform.persistence.ports import ActorKind, AuditEvent, AuditOutcome, TenantScope
from tests.unit.platform.autonomy.conftest import NOON, action, rule, subject


@dataclass(slots=True)
class RecordingActuator:
    """Performs nothing, and remembers every time it was asked to."""

    calls: list[ProposedAction] = field(default_factory=list)

    async def perform(self, proposed: ProposedAction) -> str:
        self.calls.append(proposed)
        return "performed"


@dataclass(frozen=True, slots=True)
class EngagedStop:
    """A stop that is on, whatever the configuration says."""

    def is_engaged(self, *, team_node_id: str | None = None) -> bool:
        del team_node_id
        return True

    def describe_for(self, *, team_node_id: str | None = None) -> str:
        del team_node_id
        return "automated writes are stopped for this organisation, engaged by ada"


@dataclass(slots=True)
class CollectingRecorder:
    """An audit recorder that keeps the events instead of storing them."""

    events: list[AuditEvent] = field(default_factory=list)

    async def record(
        self,
        scope: TenantScope,
        context: Any,
        *,
        action: str,
        resource_kind: str,
        resource_id: str,
        outcome: AuditOutcome = AuditOutcome.ALLOWED,
        detail: Any = None,
    ) -> AuditEvent:
        del scope
        event = AuditEvent(
            event_id=f"event-{len(self.events)}",
            occurred_at=NOON,
            actor_kind=context.actor_kind,
            actor_id=context.actor_id,
            action=action,
            resource_kind=resource_kind,
            resource_id=resource_id,
            outcome=outcome,
            detail=dict(detail or {}),
        )
        self.events.append(event)
        return event


def auditor() -> tuple[DecisionAuditor, CollectingRecorder]:
    """Return a decision auditor over a recorder the test can read."""
    recorder = CollectingRecorder()
    return (
        DecisionAuditor(
            scope=TenantScope(org_id="acme"),
            recorder=recorder,  # type: ignore[arg-type]
        ),
        recorder,
    )


@pytest.mark.parametrize("level", list(AutonomyLevel))
async def test_the_kill_switch_refuses_at_every_level_and_no_rule_overrides_it(
    level: AutonomyLevel,
) -> None:
    policies = PolicySet(rules=(rule(ScopeKind.DEPLOYMENT, level, risk_bound=RiskClass.CRITICAL),))
    actuator = RecordingActuator()
    gate = AutonomyGate(policies=policies, stop=EngagedStop(), clock=lambda: NOON)

    decision = await gate.run(action(risk=RiskClass.TRIVIAL), actuator)

    assert decision.outcome is Outcome.REFUSE
    assert decision.bound is Bound.KILL_SWITCH
    assert "No autonomy level and no approval overrides this" in decision.reason
    assert actuator.calls == []


async def test_engaging_the_stop_takes_effect_on_a_decision_not_yet_executed() -> None:
    """The state is read at the moment of the check, so there is no window."""

    @dataclass(slots=True)
    class Switchable:
        engaged: bool = False

        def is_engaged(self, *, team_node_id: str | None = None) -> bool:
            del team_node_id
            return self.engaged

        def describe_for(self, *, team_node_id: str | None = None) -> str:
            del team_node_id
            return "stopped"

    stop = Switchable()
    policies = PolicySet(rules=(rule(ScopeKind.DEPLOYMENT, AutonomyLevel.ACT_AND_REPORT),))
    gate = AutonomyGate(policies=policies, stop=stop, clock=lambda: NOON)
    actuator = RecordingActuator()

    before = await gate.decide(action())
    assert before.outcome is Outcome.EXECUTE

    stop.engaged = True
    after = await gate.run(action(), actuator)

    assert after.outcome is Outcome.REFUSE
    assert actuator.calls == []


@pytest.mark.parametrize("level", list(AutonomyLevel))
async def test_an_action_with_no_rollback_plan_needs_a_person_at_every_level(
    level: AutonomyLevel,
) -> None:
    policies = PolicySet(rules=(rule(ScopeKind.DEPLOYMENT, level, risk_bound=RiskClass.CRITICAL),))
    actuator = RecordingActuator()
    gate = AutonomyGate(policies=policies, clock=lambda: NOON)

    decision = await gate.run(action(rollback=False, risk=RiskClass.TRIVIAL), actuator)

    assert decision.needs_human
    assert decision.bound is Bound.ROLLBACK
    assert not decision.executed
    assert actuator.calls == []


async def test_a_freeze_window_refuses_whatever_the_level_says() -> None:
    policies = PolicySet(
        rules=(rule(ScopeKind.DEPLOYMENT, AutonomyLevel.ACT_AND_REPORT),),
        freezes=(
            FreezeWindow(
                name="backups",
                scope=PolicyScope(kind=ScopeKind.DEPLOYMENT),
                start=time(1, 0),
                end=time(4, 0),
            ),
        ),
    )
    actuator = RecordingActuator()
    inside = datetime(2026, 3, 12, 2, 0, tzinfo=UTC)
    gate = AutonomyGate(policies=policies, clock=lambda: inside)

    decision = await gate.run(action(), actuator)

    assert decision.outcome is Outcome.REFUSE
    assert decision.bound is Bound.FREEZE
    assert "backups" in decision.reason
    assert actuator.calls == []


async def test_a_spent_budget_downgrades_to_approval_rather_than_refusing() -> None:
    policies = PolicySet(
        rules=(rule(ScopeKind.DEPLOYMENT, AutonomyLevel.ACT_AND_REPORT),),
        budgets=(BudgetRule(name="hourly", limit=2),),
    )
    actuator = RecordingActuator()
    gate = AutonomyGate(policies=policies, clock=lambda: NOON)

    first = await gate.run(action(action_id="act-1"), actuator)
    second = await gate.run(action(action_id="act-2"), actuator)
    third = await gate.run(action(action_id="act-3"), actuator)

    assert [decision.outcome for decision in (first, second, third)] == [
        Outcome.EXECUTE,
        Outcome.EXECUTE,
        Outcome.APPROVE,
    ]
    assert third.bound is Bound.BUDGET
    assert len(actuator.calls) == 2
    assert first.budgets_spent == ("hourly:resource:ct-101",)


async def test_a_budget_only_counts_actions_that_actually_ran() -> None:
    """A refused action must not spend a limit that bounds changes."""
    policies = PolicySet(
        rules=(
            rule(ScopeKind.DEPLOYMENT, AutonomyLevel.ACT_ON_LOW_RISK, risk_bound=RiskClass.LOW),
        ),
        budgets=(BudgetRule(name="hourly", limit=1),),
    )
    actuator = RecordingActuator()
    gate = AutonomyGate(policies=policies, clock=lambda: NOON)

    above = await gate.run(action(action_id="act-1", risk=RiskClass.CRITICAL), actuator)
    within = await gate.run(action(action_id="act-2", risk=RiskClass.TRIVIAL), actuator)

    assert above.outcome is Outcome.APPROVE
    assert above.budgets_spent == ()
    assert within.outcome is Outcome.EXECUTE


async def test_a_budget_interval_survives_the_process_that_was_counting() -> None:
    """The spend lives in the audit trail, so a restart is not a fresh budget."""
    from platform.autonomy.budget import AuditSpendLedger
    from platform.persistence.fakes import FakePersistence

    gateway = FakePersistence()
    scope = TenantScope(org_id="acme")
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(scope.org_id, "Acme")
    policies = PolicySet(
        rules=(rule(ScopeKind.DEPLOYMENT, AutonomyLevel.ACT_AND_REPORT),),
        budgets=(BudgetRule(name="hourly", limit=2),),
    )
    actuator = RecordingActuator()

    before_restart = AutonomyGate(
        policies=policies,
        ledger=AuditSpendLedger(gateway=gateway, scope=scope),
        clock=lambda: NOON,
    )
    assert (await before_restart.run(action(action_id="act-1"), actuator)).executed
    assert (await before_restart.run(action(action_id="act-2"), actuator)).executed

    # A second gate over the same storage: everything in-process is gone.
    after_restart = AutonomyGate(
        policies=policies,
        ledger=AuditSpendLedger(gateway=gateway, scope=scope),
        clock=lambda: NOON + timedelta(minutes=1),
    )
    decision = await after_restart.run(action(action_id="act-3"), actuator)

    assert decision.outcome is Outcome.APPROVE
    assert decision.bound is Bound.BUDGET
    assert len(actuator.calls) == 2


async def test_a_dry_run_at_any_scope_executes_nothing_and_says_what_it_would_have_done() -> None:
    for scope_kind, fields in (
        (ScopeKind.DEPLOYMENT, {}),
        (ScopeKind.TEAM, {"team_node_id": "platform"}),
        (ScopeKind.RESOURCE, {"resource_id": "ct-101"}),
    ):
        policies = PolicySet(
            rules=(rule(scope_kind, AutonomyLevel.ACT_AND_REPORT, dry_run=True, **fields),)
        )
        actuator = RecordingActuator()
        gate = AutonomyGate(policies=policies, clock=lambda: NOON)

        decision = await gate.run(action(operation="pct stop 101"), actuator)

        assert decision.outcome is Outcome.SIMULATE, scope_kind
        assert decision.simulated
        assert not decision.executed
        assert actuator.calls == []
        assert "pct stop 101" in decision.reason


async def test_a_deployment_wide_dry_run_simulates_even_where_a_rule_does_not_say_so() -> None:
    policies = PolicySet(
        rules=(rule(ScopeKind.DEPLOYMENT, AutonomyLevel.ACT_AND_REPORT),),
        dry_run=True,
    )
    actuator = RecordingActuator()
    gate = AutonomyGate(policies=policies, clock=lambda: NOON)

    decision = await gate.run(action(), actuator)

    assert decision.outcome is Outcome.SIMULATE
    assert actuator.calls == []


async def test_a_dry_run_does_not_turn_an_approval_into_a_simulation() -> None:
    """Simulating something that would not have run says nothing useful."""
    policies = PolicySet(
        rules=(
            rule(
                ScopeKind.DEPLOYMENT,
                AutonomyLevel.ACT_ON_LOW_RISK,
                risk_bound=RiskClass.LOW,
                dry_run=True,
            ),
        )
    )
    gate = AutonomyGate(policies=policies, clock=lambda: NOON)
    decision = await gate.run(action(risk=RiskClass.CRITICAL), RecordingActuator())
    assert decision.outcome is Outcome.APPROVE


async def test_a_proposal_carries_the_exact_operation_a_person_could_run() -> None:
    gate = AutonomyGate(clock=lambda: NOON)
    decision = await gate.run(action(operation="pct unlock 101"), RecordingActuator())

    assert decision.outcome is Outcome.PROPOSE
    assert "pct unlock 101" in decision.reason
    assert decision.to_record()["action"]["operation"] == "pct unlock 101"


async def test_every_decision_is_audited_permitting_and_refusing_alike() -> None:
    recording, recorder = auditor()
    policies = PolicySet(rules=(rule(ScopeKind.DEPLOYMENT, AutonomyLevel.ACT_AND_REPORT),))
    gate = AutonomyGate(policies=policies, auditor=recording, clock=lambda: NOON)

    await gate.run(action(action_id="act-permitted"), RecordingActuator())
    gate.stop = EngagedStop()
    await gate.run(action(action_id="act-refused"), RecordingActuator())

    assert [event.action for event in recorder.events] == [
        "autonomy.decision",
        "autonomy.decision",
    ]
    assert [event.outcome for event in recorder.events] == [
        AuditOutcome.ALLOWED,
        AuditOutcome.DENIED,
    ]
    permitted, refused = recorder.events
    assert permitted.detail["decision"] == "execute"
    assert permitted.detail["winning_rule"] == "deployment:::::"
    assert permitted.detail["considered_rules"]
    assert refused.detail["refused_by"] == "kill_switch"
    assert refused.detail["reason"]
    assert refused.actor_kind is ActorKind.SYSTEM


async def test_an_expired_override_is_recorded_when_it_expires() -> None:
    recording, recorder = auditor()
    override = override_expiring(
        name="maintenance",
        scope=PolicyScope(kind=ScopeKind.TEAM, team_node_id="platform"),
        level=AutonomyLevel.ACT_AND_REPORT,
        granted_at=NOON,
        seconds=3600,
        granted_by="ada",
    )
    gate = AutonomyGate(
        policies=PolicySet(overrides=(override,)),
        auditor=recording,
        clock=lambda: NOON + timedelta(hours=2),
    )

    expired = await gate.expire_overrides()

    assert expired == ("maintenance",)
    assert [event.action for event in recorder.events] == ["autonomy.override_expired"]
    assert recorder.events[0].detail["granted_by"] == "ada"


async def test_an_override_still_in_force_is_not_reported_as_expired() -> None:
    recording, recorder = auditor()
    override = override_expiring(
        name="maintenance",
        scope=PolicyScope(kind=ScopeKind.TEAM, team_node_id="platform"),
        level=AutonomyLevel.ACT_AND_REPORT,
        granted_at=NOON,
        seconds=3600,
    )
    gate = AutonomyGate(
        policies=PolicySet(overrides=(override,)),
        auditor=recording,
        clock=lambda: NOON + timedelta(minutes=10),
    )

    assert await gate.expire_overrides() == ()
    assert recorder.events == []


async def test_deciding_performs_nothing_however_permissive_the_answer_is() -> None:
    """``decide`` is what a console calls to show what would happen."""
    policies = PolicySet(rules=(rule(ScopeKind.DEPLOYMENT, AutonomyLevel.ACT_AND_REPORT),))
    actuator = RecordingActuator()
    gate = AutonomyGate(policies=policies, ledger=InMemorySpendLedger(), clock=lambda: NOON)

    decision = await gate.decide(action())

    assert decision.outcome is Outcome.EXECUTE
    assert not decision.executed
    assert actuator.calls == []


async def test_an_action_across_resources_with_different_levels_takes_the_least_permissive() -> (
    None
):
    policies = PolicySet(
        rules=(
            rule(ScopeKind.RESOURCE, AutonomyLevel.ACT_AND_REPORT, resource_id="ct-101"),
            rule(ScopeKind.RESOURCE, AutonomyLevel.PROPOSE_ONLY, resource_id="ct-102"),
        )
    )
    actuator = RecordingActuator()
    gate = AutonomyGate(policies=policies, clock=lambda: NOON)

    decision = await gate.run(action(subjects=(subject("ct-101"), subject("ct-102"))), actuator)

    assert decision.outcome is Outcome.PROPOSE
    assert actuator.calls == []


async def test_a_spent_budget_says_out_loud_that_it_has_stopped_the_deployment() -> None:
    """Every individual action still gets an approval; the pattern is invisible."""

    @dataclass(slots=True)
    class Listening:
        raised: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)

        async def budget_exhausted(
            self, proposed: ProposedAction, *, budgets: Any, reason: str
        ) -> None:
            del reason
            self.raised.append((proposed.action_id, tuple(budgets)))

    listener = Listening()
    policies = PolicySet(
        rules=(rule(ScopeKind.DEPLOYMENT, AutonomyLevel.ACT_AND_REPORT),),
        budgets=(BudgetRule(name="hourly", limit=1),),
    )
    gate = AutonomyGate(policies=policies, exhaustion=listener, clock=lambda: NOON)
    actuator = RecordingActuator()

    await gate.run(action(action_id="act-1"), actuator)
    assert listener.raised == []

    await gate.run(action(action_id="act-2"), actuator)
    assert listener.raised == [("act-2", ("hourly:resource:ct-101",))]


async def test_nothing_is_raised_while_a_budget_still_has_room() -> None:
    policies = PolicySet(
        rules=(rule(ScopeKind.DEPLOYMENT, AutonomyLevel.ACT_AND_REPORT),),
        budgets=(BudgetRule(name="hourly", limit=5),),
    )
    gate = AutonomyGate(policies=policies, clock=lambda: NOON)
    decision = await gate.run(action(), RecordingActuator())
    assert decision.bound is None
