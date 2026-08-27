"""The remediation gate and the policy engine, driven together.

The unit suites prove the engine decides correctly and the gate orders its
checks correctly. This proves the wire between them: a level configured at a
scope really does change what the gate does with a tool call, a bound really
does refuse one, and every decision really does reach the audit trail with its
explanation on it.

Driven through ``RemediationGate.decide``, which is the one entry point every
surface reaches — the loop's hook, a console button, an operator's CLI — so what
is asserted here is what all three do.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, time
from typing import Any

import pytest

from core.capability.metadata import SideEffectLevel
from core.capability.result import CapabilityErrorClass
from platform.autonomy.bounds import BudgetRule, FreezeWindow
from platform.autonomy.decision import AutonomyGate
from platform.autonomy.levels import AutonomyLevel
from platform.autonomy.policy import PolicyRule, PolicySet
from platform.autonomy.risk import RiskClass
from platform.autonomy.scopes import PolicyScope, ScopeKind
from platform.persistence.ports import AuditEvent, AuditOutcome, TenantScope
from platform.remediation.gating import RemediationGate
from platform.remediation.models import RemediationAction, RemediationTarget

pytestmark = pytest.mark.contract

AT = datetime(2026, 3, 12, 12, 0, tzinfo=UTC)


@dataclass(slots=True)
class RecordingExecutor:
    """Stands where the executor does, and performs nothing."""

    calls: list[RemediationAction] = field(default_factory=list)

    async def execute(self, action: RemediationAction, **kwargs: Any) -> Any:
        del kwargs
        self.calls.append(action)
        raise AssertionError(
            "the contract suite's executor must not be reached with a real plan; "
            "a test that gets here is asserting the wrong thing"
        )


@dataclass(slots=True)
class CountingExecutor:
    """Records the executions and returns a result the gate can describe."""

    calls: list[RemediationAction] = field(default_factory=list)

    async def execute(self, action: RemediationAction, **kwargs: Any) -> Any:
        del kwargs
        self.calls.append(action)
        return _FakeExecution(action)


@dataclass(frozen=True, slots=True)
class _FakeExecution:
    """The shape ``_outcome_reason`` reads off an execution."""

    action: RemediationAction

    @property
    def record(self) -> Any:
        return _FakeRecord(self.action)


@dataclass(frozen=True, slots=True)
class _FakeRecord:
    action: RemediationAction
    verification: Any = None
    changed_sub_targets: tuple[str, ...] = ()
    plan_id: str = "plan-1"

    @property
    def capability(self) -> str:
        return self.action.capability

    @property
    def target(self) -> RemediationTarget:
        return self.action.target

    @property
    def outcome(self) -> Any:
        return _FakeOutcome()


@dataclass(frozen=True, slots=True)
class _FakeOutcome:
    value: str = "succeeded"


@dataclass(slots=True)
class StubRequests:
    """The request builder, reduced to what the gate asks of it."""

    queued: list[RemediationAction] = field(default_factory=list)

    async def queue(self, action: RemediationAction, **kwargs: Any) -> Any:
        del kwargs
        self.queued.append(action)
        return _Queued()

    async def build(self, action: RemediationAction, **kwargs: Any) -> Any:
        del action, kwargs
        return _Built()

    async def blast_radius(self, action: RemediationAction) -> Any:
        del action
        return _Radius()


@dataclass(frozen=True, slots=True)
class _Queued:
    change_id: str = "change-1"


@dataclass(frozen=True, slots=True)
class _Built:
    plan: Any = None
    before: Any = None


@dataclass(frozen=True, slots=True)
class _Radius:
    known: bool = True
    count: int = 1


@dataclass(slots=True)
class CollectingRecorder:
    """Keeps the audit events instead of storing them."""

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
            occurred_at=AT,
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


def an_action(
    *,
    capability: str = "restart_workload",
    risk: RiskClass = RiskClass.LOW,
    rollback: bool = True,
    action_id: str = "act-1",
) -> RemediationAction:
    """Return the action every case below is decided about."""
    return RemediationAction(
        action_id=action_id,
        capability=capability,
        target=RemediationTarget(identifier="ct-101", environment="lab", kind="container"),
        side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
        requester="ada",
        team_node_id="platform",
        risk_class=risk.value,
        rollback_planned=rollback,
        operation="pct reboot 101",
    )


def a_gate(
    policies: PolicySet,
    *,
    executor: Any = None,
    auditor: Any = None,
) -> tuple[RemediationGate, StubRequests, Any]:
    """Return a gate wired to the policy engine, and the doubles it holds."""
    from platform.autonomy.audit import DecisionAuditor

    requests = StubRequests()
    used = executor if executor is not None else CountingExecutor()
    recorder = auditor if auditor is not None else CollectingRecorder()
    gate = RemediationGate(
        requests=requests,  # type: ignore[arg-type]
        executor=used,
        autonomy=AutonomyGate(
            policies=policies,
            auditor=DecisionAuditor(
                scope=TenantScope(org_id="acme"),
                recorder=recorder,
            ),
            clock=lambda: AT,
        ),
        clock=lambda: AT,
    )
    return gate, requests, used


def rule(level: AutonomyLevel, **scope: Any) -> PolicyRule:
    """Return one rule at the scope ``scope`` names."""
    kind = scope.pop("kind", ScopeKind.DEPLOYMENT)
    return PolicyRule(scope=PolicyScope(kind=kind, **scope), level=level)


async def test_with_nothing_configured_the_gate_asks_a_person() -> None:
    gate, requests, executor = a_gate(PolicySet())

    outcome = await gate.decide(an_action())

    assert not outcome.permitted
    assert executor.calls == []
    assert len(requests.queued) == 1
    assert "waiting on a human" in outcome.reason
    assert "propose-only" in outcome.reason


async def test_a_configured_level_makes_the_gate_act_without_asking() -> None:
    gate, requests, executor = a_gate(PolicySet(rules=(rule(AutonomyLevel.ACT_AND_REPORT),)))

    outcome = await gate.decide(an_action())

    assert outcome.permitted
    assert outcome.autonomous
    assert len(executor.calls) == 1
    assert requests.queued == []


async def test_a_risk_class_above_the_bound_goes_to_approval_instead() -> None:
    gate, requests, executor = a_gate(
        PolicySet(
            rules=(
                PolicyRule(
                    scope=PolicyScope(kind=ScopeKind.DEPLOYMENT),
                    level=AutonomyLevel.ACT_ON_LOW_RISK,
                    risk_bound=RiskClass.LOW,
                ),
            )
        )
    )

    outcome = await gate.decide(an_action(risk=RiskClass.CRITICAL))

    assert not outcome.permitted
    assert executor.calls == []
    assert len(requests.queued) == 1
    assert "above the configured bound" in outcome.reason


async def test_a_freeze_window_refuses_and_names_itself() -> None:
    gate, requests, executor = a_gate(
        PolicySet(
            rules=(rule(AutonomyLevel.ACT_AND_REPORT),),
            freezes=(
                FreezeWindow(
                    name="nightly-backups",
                    scope=PolicyScope(kind=ScopeKind.DEPLOYMENT),
                    start=time(11, 0),
                    end=time(13, 0),
                ),
            ),
        )
    )

    outcome = await gate.decide(an_action())

    assert not outcome.permitted
    assert outcome.classification is CapabilityErrorClass.PERMISSION_DENIED
    assert "nightly-backups" in outcome.reason
    assert executor.calls == []
    assert requests.queued == []


async def test_an_action_with_no_rollback_plan_is_never_run_unattended() -> None:
    gate, requests, executor = a_gate(PolicySet(rules=(rule(AutonomyLevel.ACT_AND_REPORT),)))

    outcome = await gate.decide(an_action(rollback=False))

    assert not outcome.permitted
    assert executor.calls == []
    assert len(requests.queued) == 1
    assert "no rollback plan" in outcome.reason


async def test_a_dry_run_decides_and_then_performs_nothing() -> None:
    gate, requests, executor = a_gate(
        PolicySet(rules=(rule(AutonomyLevel.ACT_AND_REPORT),), dry_run=True)
    )

    outcome = await gate.decide(an_action())

    assert not outcome.permitted
    assert executor.calls == []
    assert requests.queued == []
    assert "simulated" in outcome.reason
    assert "pct reboot 101" in outcome.reason


async def test_a_budget_stops_the_third_action_and_sends_it_to_a_person() -> None:
    policies = PolicySet(
        rules=(rule(AutonomyLevel.ACT_AND_REPORT),),
        budgets=(BudgetRule(name="hourly", limit=2),),
    )
    gate, requests, executor = a_gate(policies)

    first = await gate.decide(an_action(action_id="act-1"))
    second = await gate.decide(an_action(action_id="act-2"))
    third = await gate.decide(an_action(action_id="act-3"))

    assert [decision.permitted for decision in (first, second, third)] == [True, True, False]
    assert len(executor.calls) == 2
    assert len(requests.queued) == 1
    assert "budget 'hourly'" in third.reason


async def test_every_decision_reaches_the_audit_trail_with_its_explanation() -> None:
    recorder = CollectingRecorder()
    gate, _, _ = a_gate(PolicySet(rules=(rule(AutonomyLevel.ACT_AND_REPORT),)), auditor=recorder)

    await gate.decide(an_action(action_id="act-ran"))
    await gate.decide(an_action(action_id="act-asked", rollback=False))

    assert [event.action for event in recorder.events] == [
        "autonomy.decision",
        "autonomy.decision",
    ]
    permitted, asked = recorder.events
    assert permitted.outcome is AuditOutcome.ALLOWED
    assert permitted.detail["decision"] == "execute"
    assert permitted.detail["winning_rule"] == "deployment:::::"
    assert permitted.detail["considered_rules"]
    assert asked.outcome is AuditOutcome.DENIED
    assert asked.detail["refused_by"] == "rollback"
    assert asked.detail["risk_class"] == "low"
    assert asked.detail["operation"] == "pct reboot 101"


async def test_the_resource_scope_beats_the_deployment_default_through_the_gate() -> None:
    gate, _, executor = a_gate(
        PolicySet(
            rules=(
                rule(AutonomyLevel.PROPOSE_ONLY),
                rule(AutonomyLevel.ACT_AND_REPORT, kind=ScopeKind.RESOURCE, resource_id="ct-101"),
            )
        )
    )

    outcome = await gate.decide(an_action())

    assert outcome.permitted
    assert len(executor.calls) == 1


async def test_a_gate_with_no_policy_engine_still_behaves_as_it_did() -> None:
    """The allow-list path is what a deployment mid-migration still has."""
    requests = StubRequests()
    executor = CountingExecutor()
    gate = RemediationGate(
        requests=requests,  # type: ignore[arg-type]
        executor=executor,
        clock=lambda: AT,
    )

    outcome = await gate.decide(an_action())

    assert not outcome.permitted
    assert executor.calls == []
    assert len(requests.queued) == 1
