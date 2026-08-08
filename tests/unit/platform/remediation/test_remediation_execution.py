"""Isolated, serialised, recorded per piece, and checked by reading it back.

The four claims execution makes, each asserted against something observable
rather than against a return value:

* the applier never runs outside a provisioned sandbox — asserted in the double,
  which refuses an environment it did not receive;
* two actions on one target do not interleave — asserted by timing out the
  second while the first holds the lock;
* three of five moved is ``partial``, with a plan covering three;
* an induced divergence between what was asked for and what came back is
  reported rather than swallowed.
"""

from __future__ import annotations

import asyncio

import pytest

from platform.remediation.autonomy.allow_list import AllowList, AllowListEntry, MaximumBlastRadius
from platform.remediation.autonomy.evaluation import ConditionEvaluator
from platform.remediation.errors import ConditionsNotMet, TargetLocked
from platform.remediation.execution import RemediationExecutor, TargetLocks
from platform.remediation.models import ExecutionOutcome

STAGING = "staging"
TEAM = "team-payments"


# --- Isolation ---------------------------------------------------------------


async def test_the_change_runs_inside_a_provisioned_sandbox_and_it_is_released(
    registry, plans, executor, isolation, an_action, clock
) -> None:
    """One provision, one release, and the applier saw the environment.

    The double asserts the third part itself: an applier handed anything other
    than a real ``ExecutionEnvironment`` fails there rather than here, so the
    guarantee holds for every capability rather than for the one this test drove.
    """
    action = an_action()
    before = await registry.get(action.capability).reader.read(action, at=clock())
    plan = plans.generate(action, before=before)

    await executor.execute(action, plan=plan, before=before, approval_id="change-1")

    assert isolation.entered == 1
    assert isolation.left == 1


async def test_a_sandbox_is_released_even_when_the_action_raises(
    registry, plans, verification, isolation, an_action, clock
) -> None:
    """A failed action must not leave a pod billing overnight."""

    class RaisingApplier:
        """An applier whose control plane is down."""

        async def apply(self, action, *, before, environment):
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
    executor = RemediationExecutor(
        registry=registry, isolation=isolation, verification=verification, clock=clock
    )

    action = an_action()
    before = await components.reader.read(action, at=clock())
    plan = plans.generate(action, before=before)

    with pytest.raises(RuntimeError):
        await executor.execute(action, plan=plan, before=before)

    assert isolation.entered == 1
    assert isolation.left == 1, "the sandbox outlived the action that failed inside it"


# --- Serialisation -----------------------------------------------------------


async def test_two_actions_on_one_target_are_serialised(
    registry, plans, executor, an_action, clock
) -> None:
    """The second waits, and gives up naming the first rather than waiting forever.

    An execution that hung holding the lock would block every later one with no
    symptom anybody could act on, so the wait is bounded and the timeout names
    who is holding it.
    """
    locks = TargetLocks(timeout_seconds=0.02)
    holder = asyncio.Event()

    async def hold() -> None:
        async with locks.hold("checkout-api@staging", holder="action-1"):
            holder.set()
            await asyncio.sleep(0.2)

    task = asyncio.create_task(hold())
    await holder.wait()

    with pytest.raises(TargetLocked) as refused:
        async with locks.hold("checkout-api@staging", holder="action-2"):
            pass

    assert refused.value.holder == "action-1"
    task.cancel()


async def test_two_actions_on_different_targets_do_not_block_each_other(
    clock,
) -> None:
    """The lock is per target, so an incident touching two services is not serial."""
    locks = TargetLocks(timeout_seconds=0.02)

    async with (
        locks.hold("checkout-api@staging", holder="action-1"),
        locks.hold("search-api@staging", holder="action-2"),
    ):
        assert locks.held_by("checkout-api@staging") == "action-1"
        assert locks.held_by("search-api@staging") == "action-2"


# --- Partial success ---------------------------------------------------------


async def test_a_partial_action_produces_a_plan_covering_only_what_changed(
    registry, plans, executor, plane, an_action, clock
) -> None:
    """Two of three moved, so the plan has two steps rather than three.

    A plan that still covered three would be an instruction to change something
    nobody touched — an unreviewed change carried out under the authority of a
    reviewed one.
    """
    plane.changes = 2
    action = an_action()
    before = await registry.get(action.capability).reader.read(action, at=clock())
    plan = plans.generate(action, before=before)

    assert len(plan.steps) == 3, "the plan starts out covering every sub-target"

    execution = await executor.execute(action, plan=plan, before=before, approval_id="change-1")

    assert execution.outcome is ExecutionOutcome.PARTIAL
    assert execution.record.changed_sub_targets == ("pod-1", "pod-2")
    assert len(execution.plan.steps) == 2
    assert [step.sub_target for step in execution.plan.steps] == ["pod-1", "pod-2"]
    assert [step.ordinal for step in execution.plan.steps] == [1, 2]


async def test_an_action_that_changed_nothing_produces_no_rollback_steps(
    registry, plans, executor, plane, an_action, clock
) -> None:
    """A rollback plan for a change that did not happen is an instruction to make one."""
    plane.changes = 0
    action = an_action()
    before = await registry.get(action.capability).reader.read(action, at=clock())
    plan = plans.generate(action, before=before)

    execution = await executor.execute(action, plan=plan, before=before)

    assert execution.outcome is ExecutionOutcome.FAILED
    assert execution.plan.steps == ()


async def test_every_sub_target_moving_is_a_success(
    registry, plans, executor, an_action, clock
) -> None:
    """The ordinary case, asserted so ``partial`` cannot become the only outcome."""
    action = an_action()
    before = await registry.get(action.capability).reader.read(action, at=clock())
    plan = plans.generate(action, before=before)

    execution = await executor.execute(action, plan=plan, before=before)

    assert execution.outcome is ExecutionOutcome.SUCCEEDED
    assert len(execution.plan.steps) == 3


# --- Verification ------------------------------------------------------------


async def test_verification_detects_an_induced_divergence(
    registry, plans, verification, isolation, plane, an_action, clock
) -> None:
    """The control plane accepts the change and applies something else.

    The exact failure this whole feature is about: nothing in the call path
    reported an error, and the resulting state is not the one that was approved.
    """

    class DriftingApplier:
        """An applier whose control plane quietly clamps the value."""

        async def apply(self, action, *, before, environment):
            from platform.remediation.models import SubTargetResult

            plane.values["replicas"] = 5  # a quota the request exceeded
            return tuple(
                SubTargetResult(identifier=name, changed=True) for name in before.sub_targets
            )

    components = registry.get("scale_workload")
    registry.register(
        type(components)(
            capability=components.capability,
            reader=components.reader,
            applier=DriftingApplier(),
            generator=components.generator,
            verifier=components.verifier,
            verification=components.verification,
        )
    )
    executor = RemediationExecutor(
        registry=registry, isolation=isolation, verification=verification, clock=clock
    )

    action = an_action(arguments={"replicas": 8})
    before = await components.reader.read(action, at=clock())
    plan = plans.generate(action, before=before)

    execution = await executor.execute(action, plan=plan, before=before)

    assert execution.diverged
    report = execution.record.verification
    assert report is not None
    assert not report.converged
    assert report.divergences[0].field_name == "replicas"
    assert report.divergences[0].intended == 8
    assert report.divergences[0].actual == 5
    assert "diverged from the intended state" in report.describe()


async def test_a_target_that_cannot_be_read_back_is_unverified_not_verified(
    registry, plans, executor, plane, an_action, clock
) -> None:
    """ "We could not read it back" is its own outcome and must read as one.

    Collapsing it into "no divergences found" is how an unreachable control
    plane produces a clean report.
    """

    action = an_action()
    before = await registry.get(action.capability).reader.read(action, at=clock())
    plan = plans.generate(action, before=before)

    # Readable when the action was proposed, unreadable when it is verified —
    # the ordinary shape of a control plane that went away mid-incident.
    plane.readable_reads = plane.reads

    execution = await executor.execute(action, plan=plan, before=before)

    report = execution.record.verification
    assert report is not None
    assert not report.converged
    assert "unknown" in report.describe()


# --- Conditions at execution time --------------------------------------------


async def test_an_autonomous_action_is_refused_when_its_conditions_lapsed(
    registry, plans, isolation, verification, plane, an_action, clock
) -> None:
    """The executor re-evaluates, so a console button is no way around the conditions."""
    entry = AllowListEntry(
        capability="scale_workload",
        team_node_id=TEAM,
        environments=(STAGING,),
        conditions=(MaximumBlastRadius(limit=5),),
    )
    executor = RemediationExecutor(
        registry=registry,
        isolation=isolation,
        verification=verification,
        evaluator=ConditionEvaluator(allow_list=AllowList(entries=[entry])),
        locks=TargetLocks(timeout_seconds=0.05),
        clock=clock,
    )

    action = an_action()
    before = await registry.get(action.capability).reader.read(action, at=clock())
    plan = plans.generate(action, before=before)

    with pytest.raises(ConditionsNotMet):
        await executor.execute(action, plan=plan, before=before, autonomous=True, blast_radius=19)

    assert not plane.was_applied
    assert isolation.entered == 0
