"""An autonomous execution is audited the same way an approved one is.

Not similarly. The same action name, the same resource kind, the same detail
keys — because an organisation reviewing "every production change last month"
writes one query, and a second shape would mean the autonomous half quietly did
not appear in it.

What differs is one boolean and one obligation: nobody was asked, and the team
is told afterwards. Autonomy nobody hears about is autonomy nobody can withdraw,
because the first anyone learns of it is the incident it caused.
"""

from __future__ import annotations

import pytest

from config.constants.security import (
    REMEDIATION_AUDIT_ACTION_AUTONOMOUS,
    REMEDIATION_AUDIT_ACTION_KILL_SWITCH,
    REMEDIATION_AUDIT_ACTION_WAIVER,
    REMEDIATION_AUDIT_RESOURCE_KIND,
)
from platform.identity.audit.recorder import (
    REMEDIATION_AUDIT_ACTION_EXECUTE,
    AuditRecorder,
)
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import ActorKind, AuditOutcome, TenantScope
from platform.remediation.audit import RemediationAuditor
from platform.remediation.execution import RemediationExecutor, TargetLocks
from platform.remediation.models import RollbackPlan
from platform.remediation.rollback.generator import RollbackWaiver

ORG = "acme"

#: The one capability with no derivable rollback, for the waiver path.
CLEAR = "clear_cache"


@pytest.fixture
async def gateway():
    """Yield an in-memory gateway with the organisation created."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme Corp")
    yield store
    await store.close()


@pytest.fixture
def scope() -> TenantScope:
    """Return the organisation under test."""
    return TenantScope(org_id=ORG)


@pytest.fixture
def auditor(gateway, scope, notifier, clock) -> RemediationAuditor:
    """Return an auditor writing to the in-memory store."""
    return RemediationAuditor(
        scope=scope,
        recorder=AuditRecorder(gateway=gateway, clock=clock),
        notifier=notifier,
    )


async def _events(gateway, scope):
    """Return every audit event this organisation recorded."""
    async with gateway.begin(scope) as uow:
        return await uow.audit.query(limit=50)


async def test_an_approved_and_an_autonomous_execution_produce_the_same_shape(
    registry, plans, isolation, verification, auditor, gateway, scope, an_action, clock
) -> None:
    """One query finds both, and the only difference is the ``autonomous`` flag.

    Asserted by comparing key sets rather than by reading the code, because two
    call sites writing "nearly the same" detail is exactly what drifts.
    """
    executor = RemediationExecutor(
        registry=registry,
        isolation=isolation,
        verification=verification,
        auditor=auditor,
        locks=TargetLocks(timeout_seconds=0.05),
        clock=clock,
    )

    approved = an_action(action_id="action-approved")
    before = await registry.get(approved.capability).reader.read(approved, at=clock())
    await executor.execute(
        approved,
        plan=plans.generate(approved, before=before),
        before=before,
        approval_id="change-1",
    )

    autonomous = an_action(action_id="action-autonomous")
    before = await registry.get(autonomous.capability).reader.read(autonomous, at=clock())
    await executor.execute(
        autonomous, plan=plans.generate(autonomous, before=before), before=before, autonomous=True
    )

    executions = [
        event
        for event in await _events(gateway, scope)
        if event.action == REMEDIATION_AUDIT_ACTION_EXECUTE
    ]
    assert len(executions) == 2

    first, second = sorted(executions, key=lambda event: event.resource_id)
    assert set(first.detail) == set(second.detail), "the two shapes have drifted apart"
    assert first.resource_kind == second.resource_kind == REMEDIATION_AUDIT_RESOURCE_KIND
    assert {first.detail["autonomous"], second.detail["autonomous"]} == {True, False}


async def test_an_autonomous_execution_also_raises_its_own_audit_line_and_notifies(
    registry, plans, isolation, verification, auditor, notifier, gateway, scope, an_action, clock
) -> None:
    """The extra row is what an operator filters on; the notification is the obligation."""
    executor = RemediationExecutor(
        registry=registry,
        isolation=isolation,
        verification=verification,
        auditor=auditor,
        locks=TargetLocks(timeout_seconds=0.05),
        clock=clock,
    )

    action = an_action()
    before = await registry.get(action.capability).reader.read(action, at=clock())
    await executor.execute(
        action, plan=plans.generate(action, before=before), before=before, autonomous=True
    )

    actions = [event.action for event in await _events(gateway, scope)]
    assert REMEDIATION_AUDIT_ACTION_EXECUTE in actions
    assert REMEDIATION_AUDIT_ACTION_AUTONOMOUS in actions
    assert notifier.told == [action.action_id]


async def test_an_autonomous_row_is_attributed_to_the_platform_not_to_the_agent(
    registry, plans, isolation, verification, auditor, gateway, scope, an_action, clock
) -> None:
    """The agent asked; nobody decided.

    Saying the agent decided would put a principal on the row who never had the
    authority, which is the audit trail asserting something that is not true.
    """
    executor = RemediationExecutor(
        registry=registry,
        isolation=isolation,
        verification=verification,
        auditor=auditor,
        locks=TargetLocks(timeout_seconds=0.05),
        clock=clock,
    )

    action = an_action()
    before = await registry.get(action.capability).reader.read(action, at=clock())
    await executor.execute(
        action, plan=plans.generate(action, before=before), before=before, autonomous=True
    )

    (executed,) = [
        event
        for event in await _events(gateway, scope)
        if event.action == REMEDIATION_AUDIT_ACTION_EXECUTE
    ]
    assert executed.actor_kind is ActorKind.SYSTEM
    assert executed.actor_id == auditor.autonomous_actor


async def test_an_action_that_changed_nothing_is_audited_as_allowed_not_denied(
    registry, plans, isolation, verification, auditor, gateway, scope, plane, an_action, clock
) -> None:
    """A target found already in the desired state is not a fact against it.

    Every sub-target reported ``changed=False`` because none of them needed
    moving — the action was permitted and ran; it just found nothing left to
    do. Auditing that as ``DENIED`` would read, to an operator scanning the
    trail, as an action that was refused or went wrong, when neither
    happened — the audit record must carry the same honest distinction
    ``ExecutionOutcome`` itself now makes.
    """
    plane.changes = 0
    executor = RemediationExecutor(
        registry=registry,
        isolation=isolation,
        verification=verification,
        auditor=auditor,
        locks=TargetLocks(timeout_seconds=0.05),
        clock=clock,
    )

    action = an_action()
    before = await registry.get(action.capability).reader.read(action, at=clock())
    await executor.execute(action, plan=plans.generate(action, before=before), before=before)

    (executed,) = [
        event
        for event in await _events(gateway, scope)
        if event.action == REMEDIATION_AUDIT_ACTION_EXECUTE
    ]
    assert executed.outcome is AuditOutcome.ALLOWED
    assert executed.detail["outcome"] == "unchanged"


async def test_a_genuinely_failed_execution_is_still_audited_as_denied(
    registry, isolation, verification, auditor, gateway, scope, an_action, clock
) -> None:
    """The claim the test above no longer carries: a real failure is still denied.

    Unlike "already in the desired state", this is the applier itself
    raising — the shape a control-plane outage produces — so there really is
    nothing to distinguish it from: the action did not run to completion and
    the audit trail must say so.
    """

    class RaisingApplier:
        async def apply(self, action, *, before, environment):
            del action, before, environment
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
        registry=registry,
        isolation=isolation,
        verification=verification,
        auditor=auditor,
        locks=TargetLocks(timeout_seconds=0.05),
        clock=clock,
    )

    action = an_action()
    before = await components.reader.read(action, at=clock())
    plan = RollbackPlan(
        plan_id="plan-1",
        action_id=action.action_id,
        target=str(action.target),
        recorded_state=before,
        summary="restore replicas",
    )

    with pytest.raises(RuntimeError):
        await executor.execute(action, plan=plan, before=before)

    (executed,) = [
        event
        for event in await _events(gateway, scope)
        if event.action == REMEDIATION_AUDIT_ACTION_EXECUTE
    ]
    assert executed.outcome is AuditOutcome.DENIED
    assert executed.detail["outcome"] == "failed"


async def test_a_rollback_waiver_is_audited_with_who_granted_it_and_why(
    registry, plans, auditor, gateway, scope, an_action, clock
) -> None:
    """The line is read by somebody reconstructing a decision made mid-incident."""
    action = an_action(CLEAR, arguments={"namespace": "sessions"})
    before = await registry.get(CLEAR).reader.read(action, at=clock())
    plan = plans.generate(
        action,
        before=before,
        waiver=RollbackWaiver(
            granted_by="grace", reason="the cached tokens are the established cause"
        ),
    )

    await auditor.waived(action, plan)

    (waived,) = [
        event
        for event in await _events(gateway, scope)
        if event.action == REMEDIATION_AUDIT_ACTION_WAIVER
    ]
    assert waived.detail["granted_by"] == "grace"
    assert "established cause" in waived.detail["reason"]


async def test_engaging_and_releasing_the_kill_switch_are_both_audited(
    auditor, gateway, scope, clock
) -> None:
    """The release is the more sensitive of the two, and must not go unattributed.

    It is the moment automated writes become possible again, and an audit trail
    that only recorded stops would leave the restart to somebody's memory.
    """
    from platform.remediation.autonomy.kill_switch import KillSwitch

    switch = KillSwitch()
    engaged = switch.engage(engaged_by="grace", reason="incident 4102", at=clock())
    await auditor.kill_switch(engaged, engaged=True, actor_id="grace")

    switch.release(released_by="grace")
    await auditor.kill_switch(engaged, engaged=False, actor_id="grace")

    rows = [
        event
        for event in await _events(gateway, scope)
        if event.action == REMEDIATION_AUDIT_ACTION_KILL_SWITCH
    ]
    assert len(rows) == 2
    assert {row.detail["engaged"] for row in rows} == {True, False}
