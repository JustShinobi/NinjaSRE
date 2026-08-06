"""The undo: derived before, refused on a mismatch, honest when it fails.

Four claims are made here, each about an ordering or a refusal rather than about
an output, because that is where this part of the system either works or is
theatre.

* A plan exists **before** the change, for every capability in the set.
* An action with no derivable plan is **refused**, not run with a note.
* A rollback whose target has moved **refuses** rather than applying blindly.
* A rollback that ran and did not achieve its result **raises**, and records
  which steps completed on the way.
"""

from __future__ import annotations

import pytest

from capabilities.tools.remediation import COMPONENTS
from platform.remediation.errors import (
    NoRollbackPlan,
    RollbackFailed,
    RollbackTargetMismatch,
    RollbackWindowClosed,
)
from platform.remediation.models import StateSnapshot
from platform.remediation.rollback import verification
from platform.remediation.rollback.executor import RollbackExecutor
from platform.remediation.rollback.generator import PlanFactory, RollbackWaiver

#: The capability this module drives unless it says otherwise.
SCALE = "scale_workload"

#: The one with no derivable rollback, for the waiver path.
CLEAR = "clear_cache"


# --- Derived before the action -----------------------------------------------


async def test_a_plan_is_produced_before_anything_is_applied(
    registry, plans: PlanFactory, plane, an_action, clock
) -> None:
    """The plan is written against the state that was read, and nothing has run yet.

    The ordering is the control. A plan generated after execution is a
    description of what happened; a plan generated before it is a design
    artefact the approver evaluated.
    """
    action = an_action()
    before = await registry.get(SCALE).reader.read(action, at=clock())

    plan = plans.generate(action, before=before)

    assert not plane.was_applied, "the plan was produced after the change"
    assert plan.plan_id
    assert plan.recorded_state.fingerprint == before.fingerprint
    assert "4 replica(s)" in plan.summary, plan.summary


#: The one with no derivable rollback, for the waiver path.
CLEAR = "clear_cache"
#: The capability this module drives unless it says otherwise.
SCALE = "scale_workload"


def test_every_shipped_capability_declares_a_generator() -> None:
    """All seven, because a capability without one can execute without a plan.

    The set is walked rather than spot-checked: a capability added later with
    three components instead of four fails here rather than at the moment
    somebody tries to undo it.
    """
    assert len(COMPONENTS) == 7
    for bundle in COMPONENTS:
        assert bundle.reader is not None, bundle.capability
        assert bundle.applier is not None, bundle.capability
        assert bundle.generator is not None, bundle.capability
        assert bundle.verifier is not None, bundle.capability


async def test_an_action_with_no_derivable_plan_is_refused(
    registry, plans: PlanFactory, plane, an_action, clock
) -> None:
    """A cache clear has no inverse, and the request stops rather than proceeding.

    The absence of a plan is itself the signal: an action whose undo nobody can
    write down is riskier than it looked when it was proposed, and the moment to
    notice that is before it runs.
    """
    action = an_action(CLEAR, arguments={"namespace": "sessions"})
    before = await registry.get(CLEAR).reader.read(action, at=clock())

    with pytest.raises(NoRollbackPlan):
        plans.generate(action, before=before)

    assert not plane.was_applied


async def test_an_operator_may_waive_the_requirement_and_the_waiver_is_recorded(
    registry, plans: PlanFactory, an_action, clock
) -> None:
    """The waiver is explicit, attributed, and carries a reason worth reading later."""
    action = an_action(CLEAR, arguments={"namespace": "sessions"})
    before = await registry.get(CLEAR).reader.read(action, at=clock())

    plan = plans.generate(
        action,
        before=before,
        waiver=RollbackWaiver(
            granted_by="grace",
            reason="the cached tokens are the established cause and cannot be corrected in place",
        ),
    )

    assert plan.waived
    assert plan.waived_by == "grace"
    assert not plan.is_derivable
    assert "cannot be undone" in plan.summary


def test_a_waiver_with_no_real_reason_is_refused() -> None:
    """ "n/a" is not a reason, and the audit line is read by somebody reconstructing this."""
    with pytest.raises(ValueError, match="at least"):
        RollbackWaiver(granted_by="grace", reason="ok")


async def test_an_unreadable_target_produces_no_plan(
    registry, plans: PlanFactory, plane, an_action, clock
) -> None:
    """A plan promising to restore values nobody read would write nulls into production."""
    plane.readable = False
    action = an_action()
    before = await registry.get(SCALE).reader.read(action, at=clock())

    with pytest.raises(NoRollbackPlan):
        plans.generate(action, before=before)


# --- Refused on a mismatch ---------------------------------------------------


async def test_a_rollback_refuses_when_the_target_no_longer_matches(
    registry, plans, executor, plane, step_runner, an_action, clock
) -> None:
    """Somebody else moved the workload after the action, so the plan is stale.

    Applying it anyway would not be a rollback. It would be a second unreviewed
    change, made under the authority of the first.
    """
    plan = await _executed(registry, plans, executor, an_action(), clock)
    plane.values["replicas"] = 2

    with pytest.raises(RollbackTargetMismatch):
        await RollbackExecutor(runner=step_runner(), reader=plane, clock=clock).apply(
            plan, action=an_action()
        )

    assert plane.values["replicas"] == 2, "the rollback wrote to a target it did not match"


async def test_a_rollback_refuses_when_the_target_cannot_be_read(
    registry, plans, executor, plane, step_runner, an_action, clock
) -> None:
    """An unread target is not a matching one, and treating it as one lands blind."""
    plan = await _executed(registry, plans, executor, an_action(), clock)
    plane.readable = False

    with pytest.raises(RollbackTargetMismatch):
        await RollbackExecutor(runner=step_runner(), reader=plane, clock=clock).apply(
            plan, action=an_action()
        )


async def test_the_match_check_reports_without_raising_for_a_listing(
    registry, plans, executor, plane, an_action, clock
) -> None:
    """A console showing a run's past actions needs an answer for all of them.

    A listing that raised would stop at the first stale plan, which is exactly
    the one an operator most wants to see marked as stale.
    """
    plan = await _executed(registry, plans, executor, an_action(), clock)
    plane.values["replicas"] = 2
    observed = await plane.read(an_action(), at=clock())

    report = verification.check(plan, observed)

    assert not report.matches
    assert "changed since the action ran" in report.reason


async def test_a_rollback_outside_its_window_is_refused(
    registry, plans, executor, plane, step_runner, an_action, clock
) -> None:
    """One-click rollback is for the hour after the change, not for next week.

    Later, undoing it is a fresh change against fresh state and goes through the
    approval mechanism — which is a better path than a stale handle that works.
    """
    plan = await _executed(registry, plans, executor, an_action(), clock)
    clock.advance(minutes=11)

    with pytest.raises(RollbackWindowClosed):
        await RollbackExecutor(
            runner=step_runner(),
            reader=plane,
            window_seconds=600,
            clock=clock,
        ).apply(plan, action=an_action())


# --- Applied, and honest about it --------------------------------------------


async def test_a_matching_rollback_restores_the_recorded_state(
    registry, plans, executor, plane, step_runner, an_action, clock
) -> None:
    """The steps run in order and the target comes back to what it was.

    The whole round trip: four replicas, an action taking it to eight, a plan
    that puts it back. A test that skipped the action would be checking the
    executor against a state nothing had moved.
    """
    plan = await _executed(registry, plans, executor, an_action(), clock)
    runner = step_runner()

    assert plane.values["replicas"] == 8

    result = await RollbackExecutor(runner=runner, reader=plane, clock=clock).apply(
        plan, action=an_action()
    )

    assert result.verified
    assert plane.values["replicas"] == 4
    assert result.completed == (1, 2, 3)
    assert [step.ordinal for step in runner.ran] == [1, 2, 3]


async def test_a_failing_step_stops_the_plan_and_records_what_ran(
    registry, plans, executor, plane, step_runner, an_action, clock
) -> None:
    """Continuing past a failure would run step three against state step two owed.

    And the completed list is what somebody has to reason about next, so it is
    on the exception rather than only in a log line.
    """
    plan = await _executed(registry, plans, executor, an_action(), clock)
    runner = step_runner(fail_at=2)

    with pytest.raises(RollbackFailed) as failure:
        await RollbackExecutor(runner=runner, reader=plane, clock=clock).apply(
            plan, action=an_action()
        )

    assert failure.value.completed == (1,)
    assert [step.ordinal for step in runner.ran] == [1]


async def test_a_rollback_that_ran_but_did_not_converge_raises(
    registry, plans, executor, plane, an_action, clock
) -> None:
    """Every step reporting success is not the same as the target coming back.

    The one failure mode this feature is most about: a call path where nothing
    was wrong and the conclusion was.
    """

    class SilentRunner:
        """A runner whose steps report success and change nothing."""

        async def run(self, step, *, action):
            from platform.remediation.models import SubTargetResult

            return SubTargetResult(identifier=step.sub_target, changed=True)

    plan = await _executed(registry, plans, executor, an_action(), clock)

    with pytest.raises(RollbackFailed, match="did not come back"):
        await RollbackExecutor(runner=SilentRunner(), reader=plane, clock=clock).apply(
            plan, action=an_action()
        )


async def _executed(registry, plans, executor, action, clock):
    """Run ``action`` and return the plan the executor stamped with the result.

    The plan a rollback is applied from is the one that comes *back* from an
    execution, not the one that went in: it carries the state the action left
    behind, which is what the target check compares against.
    """
    before = await registry.get(action.capability).reader.read(action, at=clock())
    plan = plans.generate(action, before=before)
    execution = await executor.execute(action, plan=plan, before=before, approval_id="change-1")
    return execution.plan


def test_an_unidentified_plan_cannot_reach_the_store(registry, an_action, clock) -> None:
    """A stored plan nothing can name again is the same as not having one."""
    from platform.remediation.models import RollbackPlan, RollbackStep

    plan = RollbackPlan(
        plan_id="",
        action_id="action-1",
        target="checkout-api",
        recorded_state=StateSnapshot(target="checkout-api", observed_at=clock()),
        steps=(RollbackStep(ordinal=1, description="put it back", capability=SCALE),),
    )

    with pytest.raises(ValueError, match="no identifier"):
        plan.to_stored("change-1")
