"""The executor owes a verification, and never leaves a target half-applied.

Two properties, and the second is the one that is hard to see afterwards.

**Every change that landed owes a verification.** The obligation is written by
the executor, from inside the same call that made the change, because that is
the only moment at which the before-values and the action are both to hand.

**An applier that raised having already changed something is put back.** A
kill switch, a partitioned control plane, or a timeout mid-apply all produce the
same shape: the call failed and the target moved. FR-012 says that must reach a
consistent state, and the executor reads the target back to find out whether it
has to.

The concurrency assertions are here too, because the declared behaviour for the
second arrival is a property of the lock the executor holds. Both behaviours are
exercised: waiting, and refusing immediately.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from core.capability.metadata import SideEffectLevel
from platform.persistence.ports.remediation_ledger import RemediationOutcome, VerificationState
from platform.remediation.aftermath import undo_of
from platform.remediation.errors import TargetLocked
from platform.remediation.execution import (
    RemediationExecutor,
    SecondArrival,
    TargetLocks,
)
from platform.remediation.models import RemediationAction, RemediationTarget, RollbackPlan
from platform.remediation.rollback.generator import PlanFactory

pytestmark = pytest.mark.unit

EPOCH = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


@dataclass(slots=True)
class RecordingObligations:
    """The narrow recorder the executor holds, as a list of what it was told."""

    before: dict[str, float] = field(default_factory=lambda: {"workload.ready_replicas": 4.0})
    owed: list[RemediationOutcome] = field(default_factory=list)
    captured: list[str] = field(default_factory=list)

    async def capture(self, action: RemediationAction) -> dict[str, float]:
        """Record that the signals were read, and return them."""
        self.captured.append(action.action_id)
        return dict(self.before)

    async def owe(
        self,
        action: RemediationAction,
        *,
        before,  # noqa: ANN001 - mirrors the protocol
        executed_at: datetime,
        autonomous: bool = False,
        plan_id: str = "",
        incident_id: str = "",
        condition_key: str = "",
        undo=None,  # noqa: ANN001 - mirrors the protocol
    ) -> RemediationOutcome:
        """Record the obligation and return it."""
        outcome = RemediationOutcome(
            action_id=action.action_id,
            capability=action.capability,
            resource_id=action.target.identifier,
            executed_at=executed_at,
            due_at=executed_at + timedelta(seconds=300),
            state=VerificationState.AWAITING,
            before=dict(before),
            plan_id=plan_id,
            autonomous=autonomous,
            undo=dict(undo) if undo else {},
        )
        self.owed.append(outcome)
        return outcome


@dataclass(slots=True)
class RecordingUndo:
    """A plan applier that records what it was asked to put back."""

    applied: list[str] = field(default_factory=list)

    async def apply(self, plan: RollbackPlan, *, action, now=None):  # noqa: ANN001, ANN202
        """Record the plan and return it."""
        self.applied.append(plan.plan_id)
        return plan


def an_action(
    *,
    action_id: str = "action-1",
    target: str = "checkout-api",
    replicas: int = 8,
) -> RemediationAction:
    """Return the action a scaling remediation proposes."""
    return RemediationAction(
        action_id=action_id,
        capability="scale_workload",
        target=RemediationTarget(identifier=target, environment="production"),
        side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
        requester="agent",
        arguments={"replicas": replicas},
        team_node_id="team-payments",
    )


async def test_a_change_that_landed_owes_a_verification_with_its_before_values(
    registry,  # noqa: ANN001 - the suite's fixtures
    isolation,
    verification,
    plans: PlanFactory,
    clock,
) -> None:
    """T-007: the obligation carries the values and the undo, and the run ends."""
    obligations = RecordingObligations()
    executor = RemediationExecutor(
        registry=registry,
        isolation=isolation,
        verification=verification,
        obligations=obligations,
        clock=clock,
    )
    action = an_action()
    components = registry.get("scale_workload")
    before = await components.reader.read(action, at=clock())
    plan = plans.generate(action, before=before)

    execution = await executor.execute(action, plan=plan, before=before, approval_id="change-1")

    assert execution.outcome.changed_anything
    assert obligations.captured == ["action-1"]
    assert len(obligations.owed) == 1
    owed = obligations.owed[0]
    assert owed.before == {"workload.ready_replicas": 4.0}
    assert owed.awaiting_verification
    undo = undo_of(owed)
    assert undo is not None
    restored_action, restored_plan = undo
    assert restored_action.action_id == "action-1"
    assert restored_plan.plan_id == plan.plan_id


async def test_an_action_that_changed_nothing_owes_nothing(
    registry,  # noqa: ANN001
    isolation,
    verification,
    plans: PlanFactory,
    clock,
    plane,
) -> None:
    """An obligation for a change that did not happen is a verdict about nothing."""

    class NothingApplier:
        """An applier that reports every sub-target unchanged."""

        async def apply(self, action, *, before, environment):  # noqa: ANN001, ANN202
            """Return no results at all."""
            return ()

    components = registry.get("scale_workload")
    registry.register(
        type(components)(
            capability=components.capability,
            reader=components.reader,
            applier=NothingApplier(),
            generator=components.generator,
            verifier=components.verifier,
            verification=components.verification,
        )
    )
    obligations = RecordingObligations()
    executor = RemediationExecutor(
        registry=registry,
        isolation=isolation,
        verification=verification,
        obligations=obligations,
        clock=clock,
    )
    action = an_action()
    before = await components.reader.read(action, at=clock())
    plan = plans.generate(action, before=before)

    execution = await executor.execute(action, plan=plan, before=before)

    assert not execution.outcome.changed_anything
    assert obligations.owed == []


async def test_an_applier_that_raised_having_changed_the_target_is_put_back(
    registry,  # noqa: ANN001
    isolation,
    verification,
    plans: PlanFactory,
    clock,
    plane,
) -> None:
    """FR-012 and T-019: never abandoned half-applied, whatever interrupted it."""

    @dataclass(slots=True)
    class HalfApplier:
        """Changes the target and then fails, as a kill switch mid-apply does."""

        plane: object

        async def apply(self, action, *, before, environment):  # noqa: ANN001, ANN202
            """Move the target, then raise."""
            self.plane.values["replicas"] = 8
            raise RuntimeError("the kill switch engaged while this was running")

    components = registry.get("scale_workload")
    registry.register(
        type(components)(
            capability=components.capability,
            reader=components.reader,
            applier=HalfApplier(plane=plane),
            generator=components.generator,
            verifier=components.verifier,
            verification=components.verification,
        )
    )
    undo = RecordingUndo()
    executor = RemediationExecutor(
        registry=registry,
        isolation=isolation,
        verification=verification,
        undo=undo,
        clock=clock,
    )
    action = an_action()
    before = await components.reader.read(action, at=clock())
    plan = plans.generate(action, before=before)

    with pytest.raises(RuntimeError):
        await executor.execute(action, plan=plan, before=before)

    assert undo.applied == [plan.plan_id]


async def test_an_applier_that_raised_without_changing_anything_is_left_alone(
    registry,  # noqa: ANN001
    isolation,
    verification,
    plans: PlanFactory,
    clock,
) -> None:
    """Undoing a change that never happened would itself be an unreviewed write."""

    class RaisingApplier:
        """Fails before touching anything."""

        async def apply(self, action, *, before, environment):  # noqa: ANN001, ANN202
            """Raise without changing the target."""
            raise RuntimeError("the control plane refused the connection")

    components = registry.get("scale_workload")
    registry.register(
        type(components)(
            capability=components.capability,
            reader=components.reader,
            applier=RaisingApplier(),
            generator=components.generator,
            verifier=components.verifier,
            verification=components.verification,
        )
    )
    undo = RecordingUndo()
    executor = RemediationExecutor(
        registry=registry,
        isolation=isolation,
        verification=verification,
        undo=undo,
        clock=clock,
    )
    action = an_action()
    before = await components.reader.read(action, at=clock())
    plan = plans.generate(action, before=before)

    with pytest.raises(RuntimeError):
        await executor.execute(action, plan=plan, before=before)

    assert undo.applied == []


async def test_a_second_arrival_waits_when_that_is_what_was_declared() -> None:
    """T-030, one way round: the second action queues behind the first."""
    locks = TargetLocks(on_conflict=SecondArrival.WAIT, timeout_seconds=1.0)
    order: list[str] = []

    async def hold(name: str, seconds: float) -> None:
        async with locks.hold("checkout-api", holder=name):
            order.append(f"{name}:in")
            await asyncio.sleep(seconds)
            order.append(f"{name}:out")

    first = asyncio.create_task(hold("action-1", 0.05))
    await asyncio.sleep(0)
    second = asyncio.create_task(hold("action-2", 0.0))
    await asyncio.gather(first, second)

    assert order == ["action-1:in", "action-1:out", "action-2:in", "action-2:out"]


async def test_a_second_arrival_is_refused_immediately_when_that_is_declared() -> None:
    """T-030, the other way: refused, naming who holds it, without waiting."""
    locks = TargetLocks(on_conflict=SecondArrival.REFUSE, timeout_seconds=30.0)

    async def refused() -> None:
        async with locks.hold("checkout-api", holder="action-2"):
            pass

    async with locks.hold("checkout-api", holder="action-1"):
        with pytest.raises(TargetLocked) as second:
            await refused()

    assert "action-1" in str(second.value)
    assert "still held after 0s" in str(second.value)


async def test_a_durable_hold_another_replica_owns_refuses_the_second_replica() -> None:
    """FR-021 across replicas, through the seam a deployment supplies."""

    @dataclass(slots=True)
    class OneHolder:
        """A durable hold that has already been taken by somebody else."""

        holder: str = "another-replica"
        released: list[str] = field(default_factory=list)

        async def acquire(self, target: str, *, holder: str) -> bool:
            """Refuse, because this target is held elsewhere."""
            return False

        async def release(self, target: str, *, holder: str) -> None:
            """Record the release."""
            self.released.append(target)

    locks = TargetLocks(durable=OneHolder())

    with pytest.raises(TargetLocked, match="another replica"):
        async with locks.hold("checkout-api", holder="action-1"):
            pass

    # The in-process lock is released again, or the refusal would deadlock the
    # replica against a target another one happens to hold.
    assert not locks.locks["checkout-api"].locked()
