"""What each verdict causes, and — more importantly — what it does not.

Four of the five verdicts write nothing. That is the property this file spends
most of its assertions on, because the tempting generalisation is "the action
did not help, so undo it", and undoing an action that merely did nothing is a
second unattended write with no evidence behind it.

The rest is the failure cascade. A rollback that fails escalates at the highest
severity, records both failures, and suspends autonomous action on the resource
until a person clears it — and autonomy resumes only after that clearing, which
is asserted rather than assumed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from core.capability.metadata import SideEffectLevel
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import TenantScope
from platform.persistence.ports.remediation_ledger import (
    RemediationOutcome,
    RollbackDisposition,
    VerificationState,
    VerificationVerdict,
)
from platform.remediation.aftermath import (
    ESCALATION_SEVERITY,
    HIGHEST_SEVERITY,
    Aftermath,
    VerificationAftermath,
    undo_payload,
)
from platform.remediation.errors import RollbackFailed, RollbackTargetMismatch
from platform.remediation.models import (
    RemediationAction,
    RemediationTarget,
    RollbackPlan,
    RollbackStep,
    StateSnapshot,
)
from platform.remediation.obligations import Verification
from platform.remediation.recurrence import RecurrenceRule, RecurrenceWatch
from platform.remediation.suspension import AutonomySuspensions

pytestmark = pytest.mark.unit

EPOCH = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def at(seconds: float = 0.0) -> datetime:
    """Return a fixed instant offset by ``seconds``."""
    return EPOCH + timedelta(seconds=seconds)


def an_action(*, action_id: str = "action-1") -> RemediationAction:
    """Return the action a scaling remediation proposes."""
    return RemediationAction(
        action_id=action_id,
        capability="scale_workload",
        target=RemediationTarget(identifier="checkout-api", environment="production"),
        side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
        requester="agent",
        team_node_id="team-payments",
    )


def a_plan(action: RemediationAction) -> RollbackPlan:
    """Return a plan that reverses ``action`` and is derivable."""
    return RollbackPlan(
        plan_id="plan-1",
        action_id=action.action_id,
        target=str(action.target),
        recorded_state=StateSnapshot(target=str(action.target), observed_at=at(), values={"n": 4}),
        summary="scale checkout-api in production back to 4 replicas",
        steps=(
            RollbackStep(
                ordinal=1,
                description="scale back to 4",
                capability="scale_workload",
                arguments={"replicas": 4},
            ),
        ),
        created_at=at(),
    )


def an_outcome(
    *,
    action_id: str = "action-1",
    capability: str = "scale_workload",
    resource_id: str = "checkout-api",
    minutes: float = 0.0,
    with_undo: bool = True,
) -> RemediationOutcome:
    """Return a verified ledger row, optionally carrying its undo payload."""
    action = an_action(action_id=action_id)
    return RemediationOutcome(
        action_id=action_id,
        capability=capability,
        resource_id=resource_id,
        condition_key="replica-shortfall",
        team_node_id="team-payments",
        incident_id="incident-1",
        plan_id="plan-1",
        executed_at=at(minutes * 60),
        due_at=at(minutes * 60 + 300),
        settle_seconds=300,
        state=VerificationState.VERIFIED,
        verdict=VerificationVerdict.WORSENED,
        signal_names=("workload.ready_replicas",),
        before={"workload.ready_replicas": 4.0},
        after={"workload.ready_replicas": 1.0},
        autonomous=True,
        undo=undo_payload(action, a_plan(action)) if with_undo else {},
    )


def a_verification(outcome: RemediationOutcome, verdict: VerificationVerdict) -> Verification:
    """Return the verification that reached ``verdict`` about ``outcome``."""
    from dataclasses import replace

    return Verification(
        outcome=replace(outcome, verdict=verdict),
        verdict=verdict,
        before=dict(outcome.before),
        after=dict(outcome.after),
    )


@dataclass(slots=True)
class RecordingApplier:
    """A plan applier that records what it was asked to undo, or raises."""

    applied: list[str] = field(default_factory=list)
    raises: Exception | None = None

    async def apply(self, plan, *, action, now=None):  # noqa: ANN001, ANN202 - test double
        """Record the plan, or raise whatever this double was configured with."""
        if self.raises is not None:
            raise self.raises
        self.applied.append(plan.plan_id)
        return plan


@dataclass(slots=True)
class RecordingListener:
    """Whatever the deployment tells, as a list of what it was told."""

    resolved_with: list[Aftermath] = field(default_factory=list)
    escalated_with: list[Aftermath] = field(default_factory=list)
    patterns: list[object] = field(default_factory=list)

    async def resolved(self, aftermath: Aftermath) -> None:
        """Record a resolution."""
        self.resolved_with.append(aftermath)

    async def escalated(self, aftermath: Aftermath) -> None:
        """Record an escalation."""
        self.escalated_with.append(aftermath)

    async def recurrence(self, problem: object) -> None:
        """Record a raised pattern."""
        self.patterns.append(problem)


@pytest.fixture
async def storage() -> FakePersistence:
    """Return an in-memory store with one organisation."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme Corp")
    return store


@pytest.fixture
def listener() -> RecordingListener:
    """Return the listener every test asserts against."""
    return RecordingListener()


def aftermath_over(
    unit,  # noqa: ANN001 - the fake unit of work
    storage: FakePersistence,
    listener: RecordingListener,
    *,
    applier: RecordingApplier | None = None,
    recurrence: RecurrenceWatch | None = None,
) -> VerificationAftermath:
    """Return the aftermath service wired over one unit of work."""
    return VerificationAftermath(
        ledger=unit.remediation,
        suspensions=AutonomySuspensions(audit=unit.audit, clock=lambda: at(600)),
        recurrence=recurrence,
        applier=applier,
        listener=listener,
        clock=lambda: at(600),
    )


async def test_an_effective_action_closes_its_incident_with_the_values(
    storage: FakePersistence,
    listener: RecordingListener,
) -> None:
    """SC-001: the before and after values travel with the resolution."""
    async with storage.begin(TenantScope(org_id="acme")) as unit:
        outcome = await unit.remediation.record(an_outcome())
        result = await aftermath_over(unit, storage, listener).apply(
            a_verification(outcome, VerificationVerdict.EFFECTIVE)
        )

    assert result.resolved
    assert not result.escalated
    assert result.rollback is RollbackDisposition.NOT_REQUIRED
    assert listener.resolved_with == [result]
    assert result.to_record()["before"] == {"workload.ready_replicas": 4.0}
    assert result.to_record()["after"] == {"workload.ready_replicas": 1.0}


async def test_an_ineffective_action_escalates_and_is_not_rolled_back(
    storage: FakePersistence,
    listener: RecordingListener,
) -> None:
    """SC-002 and T-020: an action that did nothing is left in place."""
    applier = RecordingApplier()

    async with storage.begin(TenantScope(org_id="acme")) as unit:
        outcome = await unit.remediation.record(an_outcome())
        result = await aftermath_over(unit, storage, listener, applier=applier).apply(
            a_verification(outcome, VerificationVerdict.INEFFECTIVE)
        )

    assert result.escalated
    assert result.severity == ESCALATION_SEVERITY
    assert result.rollback is RollbackDisposition.NOT_REQUIRED
    assert applier.applied == []
    assert listener.escalated_with == [result]


async def test_an_inconclusive_verification_is_not_rolled_back_either(
    storage: FakePersistence,
    listener: RecordingListener,
) -> None:
    """T-020: no evidence the change was harmful is not evidence it was."""
    applier = RecordingApplier()

    async with storage.begin(TenantScope(org_id="acme")) as unit:
        outcome = await unit.remediation.record(an_outcome())
        result = await aftermath_over(unit, storage, listener, applier=applier).apply(
            a_verification(outcome, VerificationVerdict.INCONCLUSIVE)
        )

    assert applier.applied == []
    assert result.escalated
    assert not result.resolved


async def test_a_worsened_verification_rolls_back_automatically(
    storage: FakePersistence,
    listener: RecordingListener,
) -> None:
    """SC-003 and T-014: the only verdict that writes anything."""
    applier = RecordingApplier()

    async with storage.begin(TenantScope(org_id="acme")) as unit:
        outcome = await unit.remediation.record(an_outcome())
        result = await aftermath_over(unit, storage, listener, applier=applier).apply(
            a_verification(outcome, VerificationVerdict.WORSENED)
        )
        stored = await unit.remediation.get("action-1")

    assert applier.applied == ["plan-1"]
    assert result.rollback is RollbackDisposition.ROLLED_BACK
    assert stored is not None
    assert stored.rollback is RollbackDisposition.ROLLED_BACK


async def test_a_rollback_that_is_no_longer_possible_says_so_explicitly(
    storage: FakePersistence,
    listener: RecordingListener,
) -> None:
    """FR-011 and T-018: the world moved on, and that is a different fact."""
    applier = RecordingApplier(
        raises=RollbackTargetMismatch(
            "plan-1", "checkout-api@production", expected="abc123", observed="def456"
        )
    )

    async with storage.begin(TenantScope(org_id="acme")) as unit:
        outcome = await unit.remediation.record(an_outcome())
        result = await aftermath_over(unit, storage, listener, applier=applier).apply(
            a_verification(outcome, VerificationVerdict.WORSENED)
        )

    assert result.rollback is RollbackDisposition.IMPOSSIBLE
    assert "no longer matches" in result.rollback_detail
    assert result.severity == HIGHEST_SEVERITY
    assert result.escalated


async def test_an_action_with_no_recorded_plan_says_the_rollback_is_impossible(
    storage: FakePersistence,
    listener: RecordingListener,
) -> None:
    """FR-011: skipping silently is the failure mode; saying so is the requirement."""
    applier = RecordingApplier()

    async with storage.begin(TenantScope(org_id="acme")) as unit:
        outcome = await unit.remediation.record(an_outcome(with_undo=False))
        result = await aftermath_over(unit, storage, listener, applier=applier).apply(
            a_verification(outcome, VerificationVerdict.WORSENED)
        )

    assert applier.applied == []
    assert result.rollback is RollbackDisposition.IMPOSSIBLE
    assert "no derivable rollback plan" in result.rollback_detail


async def test_a_failed_rollback_escalates_highest_and_suspends_the_resource(
    storage: FakePersistence,
    listener: RecordingListener,
) -> None:
    """SC-004 and T-016: both failures recorded, and nothing autonomous after."""
    applier = RecordingApplier(
        raises=RollbackFailed("plan-1", completed=(1,), detail="the control plane refused.")
    )

    async with storage.begin(TenantScope(org_id="acme")) as unit:
        outcome = await unit.remediation.record(an_outcome())
        result = await aftermath_over(unit, storage, listener, applier=applier).apply(
            a_verification(outcome, VerificationVerdict.WORSENED)
        )

    assert result.rollback is RollbackDisposition.FAILED
    assert result.severity == HIGHEST_SEVERITY
    assert result.suspended
    # Both failures: the action that made things worse, and the undo that did not.
    assert "workload.ready_replicas 4 → 1" in result.describe()
    assert "the automatic rollback also failed" in result.describe().lower()

    async with storage.begin(TenantScope(org_id="acme")) as unit:
        live = await AutonomySuspensions(audit=unit.audit).current("checkout-api")
    assert live is not None
    assert live.action_id == "action-1"
    assert "rollback failed" in live.reason


async def test_a_suspension_is_visible_in_the_listing_and_cleared_by_a_person(
    storage: FakePersistence,
) -> None:
    """T-017: autonomy resumes only after a human clears it, and never on a timer."""
    async with storage.begin(TenantScope(org_id="acme")) as unit:
        suspensions = AutonomySuspensions(audit=unit.audit, clock=lambda: at(0))
        await suspensions.suspend(
            "checkout-api", reason="the rollback failed", action_id="action-1"
        )

        listed = await suspensions.all()
        assert [item.resource_id for item in listed] == ["checkout-api"]
        assert await suspensions.current("checkout-api") is not None

        cleared = await suspensions.clear(
            "checkout-api",
            principal_id="ada",
            reason="replica count restored by hand and the workload is healthy",
            at=at(3600),
        )

        assert cleared is not None
        assert cleared.cleared_by == "ada"
        assert await suspensions.current("checkout-api") is None
        assert await suspensions.all() == ()
        assert [item.resource_id for item in await suspensions.all(live_only=False)] == [
            "checkout-api"
        ]


async def test_a_suspension_without_a_reason_is_refused(storage: FakePersistence) -> None:
    """An unexplained suspension is a stopped resource with nothing to act on."""
    async with storage.begin(TenantScope(org_id="acme")) as unit:
        suspensions = AutonomySuspensions(audit=unit.audit)

        with pytest.raises(ValueError, match="must say why"):
            await suspensions.suspend("checkout-api", reason="  ")


async def test_clearing_a_resource_that_was_never_suspended_is_not_an_error(
    storage: FakePersistence,
) -> None:
    """Making the safe thing produce a stack trace is how it stops being done."""
    async with storage.begin(TenantScope(org_id="acme")) as unit:
        suspensions = AutonomySuspensions(audit=unit.audit)

        assert (
            await suspensions.clear("checkout-api", principal_id="ada", reason="nothing to do")
            is None
        )


async def test_the_fourth_identical_remediation_raises_a_recurring_problem(
    storage: FakePersistence,
    listener: RecordingListener,
) -> None:
    """SC-007 and T-026: four in the window is a pattern, not a fourth incident."""
    async with storage.begin(TenantScope(org_id="acme")) as unit:
        watch = RecurrenceWatch(
            ledger=unit.remediation,
            default_rule=RecurrenceRule(threshold=4, window_seconds=30 * 86_400),
            clock=lambda: at(600),
        )
        service = aftermath_over(unit, storage, listener, recurrence=watch)

        results = []
        for index in range(4):
            outcome = await unit.remediation.record(
                an_outcome(action_id=f"action-{index}", minutes=index)
            )
            results.append(
                await service.apply(a_verification(outcome, VerificationVerdict.EFFECTIVE))
            )

        live = await unit.remediation.open_problem_for("scale_workload@checkout-api")

    assert [result.problem is None for result in results] == [True, True, True, False]
    assert live is not None
    assert live.occurrences == 4
    assert live.suppressing
    assert listener.patterns == [live]


async def test_a_recurring_problem_is_a_different_noun_and_closed_by_a_change(
    storage: FakePersistence,
) -> None:
    """T-027 and FR-018: it names a pattern, and a close names the change."""
    async with storage.begin(TenantScope(org_id="acme")) as unit:
        watch = RecurrenceWatch(
            ledger=unit.remediation,
            default_rule=RecurrenceRule(threshold=2, window_seconds=30 * 86_400),
            clock=lambda: at(600),
        )
        for index in range(2):
            outcome = await unit.remediation.record(
                an_outcome(action_id=f"action-{index}", minutes=index)
            )
        problem = await watch.observe(outcome, now=at(600))
        assert problem is not None

        assert await watch.suppressing("scale_workload", "checkout-api") is not None

        closed = await watch.close(
            problem.problem_id,
            principal_id="ada",
            change="raised the replica floor to 8 in the deployment manifest",
            at=at(7200),
        )

        assert await watch.suppressing("scale_workload", "checkout-api") is None

    assert closed.close_reason.startswith("raised the replica floor")
    assert closed.closed_by == "ada"
    assert not closed.is_live
    assert problem.pattern_key == "scale_workload@checkout-api"
    assert problem.action_ids


async def test_recurrence_is_per_resource_and_capability_not_global(
    storage: FakePersistence,
) -> None:
    """FR-020: four different things happening once is not a pattern."""
    async with storage.begin(TenantScope(org_id="acme")) as unit:
        watch = RecurrenceWatch(
            ledger=unit.remediation,
            default_rule=RecurrenceRule(threshold=4, window_seconds=30 * 86_400),
            clock=lambda: at(600),
        )
        for index in range(4):
            await unit.remediation.record(
                an_outcome(
                    action_id=f"action-{index}",
                    resource_id=f"checkout-api-{index}",
                    minutes=index,
                )
            )
        last = await unit.remediation.get("action-3")
        assert last is not None
        problem = await watch.observe(last, now=at(600))

    assert problem is None


async def test_a_recurrence_window_can_be_tuned_per_capability(
    storage: FakePersistence,
) -> None:
    """T-029: the count and the window are the deployment's, per capability."""
    async with storage.begin(TenantScope(org_id="acme")) as unit:
        watch = RecurrenceWatch(
            ledger=unit.remediation,
            rules={"scale_workload": RecurrenceRule(threshold=2, window_seconds=3600)},
            default_rule=RecurrenceRule(threshold=10, window_seconds=30 * 86_400),
            clock=lambda: at(600),
        )
        for index in range(2):
            outcome = await unit.remediation.record(
                an_outcome(action_id=f"action-{index}", minutes=index)
            )
        problem = await watch.observe(outcome, now=at(600))

    assert watch.rule_for("scale_workload").threshold == 2
    assert watch.rule_for("restart_workload").threshold == 10
    assert problem is not None
    assert problem.window_seconds == 3600
