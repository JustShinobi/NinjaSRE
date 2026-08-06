"""The gate, end to end, against the real approval machinery and a real store.

Nothing here is a double except the control plane and the sandbox. The approval
service is feature 015's, the persistence is the in-memory gateway that passes
the same contract suite as PostgreSQL, and the decision is made by a real
principal through the real ``decide``. That matters: the claims being made are
about the *interaction* of the gate and the approval mechanism, and a mocked
approval would let both drift.

The ordering under test is the one the plan specifies, and each test names the
step it is about: kill switch, allow-list, approval, plan persisted,
re-evaluation, execute, verify.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from config.constants.security import REMEDIATION_APPROVAL_EXPIRY_SECONDS
from core.capability.result import CapabilityErrorClass
from platform.approvals.models import ChangeState, ChangeType, PendingChange
from platform.approvals.service import ApprovalService
from platform.identity.authorisation import PermissionSet
from platform.identity.models import Grant, Principal
from platform.identity.permissions import Role
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import PrincipalKind, TenantScope
from platform.remediation.autonomy.allow_list import AllowList, AllowListEntry, TargetPattern
from platform.remediation.autonomy.evaluation import ConditionEvaluator
from platform.remediation.execution import RemediationApplier
from platform.remediation.gating import RemediationGate, RunContext
from platform.remediation.models import ExecutionOutcome
from platform.remediation.request import RequestBuilder
from platform.remediation.rollback.generator import PlanFactory

ORG = "acme"
REQUESTER = "ada"
REVIEWER = "grace"
STAGING = "staging"
TEAM = "team-payments"

#: The one capability with no derivable rollback.
CLEAR = "clear_cache"


@dataclass(slots=True)
class ImmediateDecision:
    """A waiter that answers the moment it is asked, the way a human would not.

    Real suspension is a deployment's concern — a queue, a poll, an event — and
    what this suite is about is what the gate does with each answer. Standing in
    for the wait rather than for the *decision* is what keeps the approval
    service real in these tests.
    """

    service: ApprovalService
    approve: bool = True
    reason: str | None = None
    expire: bool = False
    waited: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.waited = []

    async def wait(self, change_id: str, *, timeout_seconds: float) -> PendingChange:
        """Decide ``change_id`` immediately and return it as decided."""
        self.waited.append(change_id)
        if self.expire:
            (expired,) = await self.service.expire_due(self.service.clock() + _past_the_window())
            return expired
        return await self.service.decide(
            change_id,
            approver=_a_principal(REVIEWER),
            permissions=_held_by(REVIEWER, Role.RESPONDER),
            approve=self.approve,
            reason=self.reason,
        )


def _past_the_window():
    from datetime import timedelta

    return timedelta(seconds=REMEDIATION_APPROVAL_EXPIRY_SECONDS + 60)


def _a_principal(principal_id: str) -> Principal:
    """Return a human principal in the organisation under test."""
    return Principal(
        principal_id=principal_id,
        org_id=ORG,
        kind=PrincipalKind.USER,
        display_name=principal_id,
    )


def _held_by(principal_id: str, role: Role) -> PermissionSet:
    """Return what ``principal_id`` holds, as one grant at the organisation."""
    return PermissionSet(
        grants=(
            Grant(
                grant_id=f"{principal_id}-{role.value}",
                principal_id=principal_id,
                role=role,
                node_id=None,
            ),
        )
    )


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
def approvals(gateway, scope, registry, clock) -> ApprovalService:
    """Return the real approval service, with remediation wired into its applier map."""
    return ApprovalService(
        gateway=gateway,
        scope=scope,
        appliers={ChangeType.REMEDIATION: RemediationApplier(registry=registry, clock=clock)},
        clock=clock,
    )


@pytest.fixture
def requests(registry, plans: PlanFactory, approvals, gateway, scope, clock) -> RequestBuilder:
    """Return a request builder wired to the real approval service and store."""
    return RequestBuilder(
        registry=registry,
        plans=plans,
        approvals=approvals,
        gateway=gateway,
        scope=scope,
        clock=clock,
    )


def _gate(requests, executor, clock, **fields) -> RemediationGate:
    """Return a gate for the run under test, with whatever the test varies."""
    return RemediationGate(
        requests=requests,
        executor=executor,
        run=RunContext(requester=REQUESTER, team_node_id=TEAM, environment=STAGING),
        clock=clock,
        **fields,
    )


# --- The approved path -------------------------------------------------------


async def test_an_approved_action_runs_and_its_plan_was_stored_first(
    requests, executor, approvals, gateway, scope, plane, an_action, clock
) -> None:
    """The whole sequence, in order, with the plan in the store before the change.

    The plan's presence is asserted from the store rather than from the object
    the gate returned, because a plan that only existed in memory is one that a
    restart between the approval and the execution would lose.
    """
    gate = _gate(requests, executor, clock, waiter=ImmediateDecision(service=approvals))

    outcome = await gate.decide(an_action())

    assert outcome.permitted
    assert outcome.approval_id
    assert outcome.execution is not None
    assert outcome.execution.outcome is ExecutionOutcome.SUCCEEDED
    assert plane.was_applied

    async with gateway.begin(scope) as uow:
        stored = await uow.approvals.rollback_plan_for(outcome.approval_id)
    assert stored is not None, "the change ran with no plan in the store"
    assert stored.steps, "the stored plan has no steps"


async def test_the_request_carries_state_blast_radius_plan_and_evidence(
    requests, an_action, clock
) -> None:
    """Everything FR-005 names, asserted on the built request rather than on a render.

    A reviewer shown "restart checkout-api?" learns to click. What makes the
    decision real is the rest of it, so the rest of it is what is checked.
    """
    request = await requests.build(an_action())

    assert request.before.known
    assert request.before.values == {"replicas": 4}
    assert request.plan.steps
    assert request.action.evidence
    assert "memory rose steadily" in request.rationale()
    assert "Undo:" in request.rationale()
    # The graph is reachable and holds no edges for this workload, which is a
    # real answer and reads as one. It is *not* the same as an unreachable
    # graph, which the next test is about.
    assert request.blast_radius.known
    assert request.blast_radius.count == 0
    assert "Nothing recorded in the topology graph" in request.blast_radius.describe()


async def test_an_unreachable_graph_reports_the_radius_as_unknown_rather_than_empty(
    registry, plans: PlanFactory, an_action
) -> None:
    """The one reassurance a missing input must never give.

    "Nothing depends on this" is what a reviewer reads fastest and questions
    least, and a builder with nowhere to ask must not produce it.
    """
    unwired = RequestBuilder(registry=registry, plans=plans)

    radius = await unwired.blast_radius(an_action())

    assert not radius.known
    assert "unknown, not small" in radius.describe()


async def test_a_remediation_approval_expires_sooner_than_a_configuration_change(
    requests, approvals, an_action, clock
) -> None:
    """Incident timescales, not the three days a prompt change gets.

    An approval that arrives forty minutes late applies to a cluster that has
    already moved, and default-deny on expiry is the safe direction.
    """
    request = await requests.queue(an_action())
    change = await approvals.get(request.change_id)

    window = (change.expires_at - change.created_at).total_seconds()

    assert window == pytest.approx(REMEDIATION_APPROVAL_EXPIRY_SECONDS)
    assert window < approvals.policy.change_expiry_hours * 3600


# --- The refused paths -------------------------------------------------------


async def test_a_declined_action_does_not_run_and_the_investigation_continues(
    requests, executor, approvals, plane, an_action, clock
) -> None:
    """A refusal is a value the agent can reason about, not the end of the run.

    An agent that stopped because a mitigation was declined would throw away the
    diagnosis it had already reached, which is most of what the investigation
    was for.
    """
    gate = _gate(
        requests,
        executor,
        clock,
        waiter=ImmediateDecision(
            service=approvals, approve=False, reason="we are mid-deploy already"
        ),
    )

    outcome = await gate.decide(an_action())

    assert not outcome.permitted
    assert not plane.was_applied
    assert outcome.classification is CapabilityErrorClass.APPROVAL_REQUIRED
    assert "declined by a human" in outcome.reason
    assert "we are mid-deploy already" in outcome.reason
    assert "Continue the investigation without it" in outcome.reason


async def test_an_expired_approval_does_not_run_and_says_nobody_answered(
    requests, executor, approvals, plane, an_action, clock
) -> None:
    """Default-deny on expiry, and the model is told which of the two happened.

    "Declined" and "nobody answered" read very differently to the agent deciding
    whether to propose something else.
    """
    gate = _gate(
        requests, executor, clock, waiter=ImmediateDecision(service=approvals, expire=True)
    )

    outcome = await gate.decide(an_action())

    assert not outcome.permitted
    assert not plane.was_applied
    assert "expired without a decision" in outcome.reason


async def test_the_kill_switch_refuses_before_an_approval_is_even_raised(
    requests, executor, approvals, plane, an_action, clock
) -> None:
    """Nobody is interrupted for a change that could not run anyway.

    And the classification says "do not retry" rather than "wait", because
    waiting for a human while writes are stopped is waiting for nothing.
    """
    waiter = ImmediateDecision(service=approvals)
    gate = _gate(requests, executor, clock, waiter=waiter)
    gate.kill_switch.engage(engaged_by=REVIEWER, reason="incident 4102", at=clock())

    outcome = await gate.decide(an_action())

    assert not outcome.permitted
    assert not plane.was_applied
    assert waiter.waited == [], "a human was asked about a change the switch had already stopped"
    assert outcome.classification is CapabilityErrorClass.PERMISSION_DENIED


async def test_an_action_with_no_derivable_plan_never_reaches_a_reviewer(
    requests, executor, approvals, plane, an_action, clock
) -> None:
    """Refused at the request, before an interruption is spent on it.

    A request that reached a reviewer and then turned out to be unapprovable is
    an interruption spent on nothing, during an incident.
    """
    waiter = ImmediateDecision(service=approvals)
    gate = _gate(requests, executor, clock, waiter=waiter)

    outcome = await gate.decide(an_action(CLEAR, arguments={"namespace": "sessions"}))

    assert not outcome.permitted
    assert not plane.was_applied
    assert waiter.waited == []
    assert outcome.classification is CapabilityErrorClass.PERMISSION_DENIED
    assert "no derivable rollback plan" in outcome.reason


# --- The autonomous path -----------------------------------------------------


async def test_an_allow_listed_action_runs_without_asking_anybody(
    requests, executor, approvals, plane, an_action, clock
) -> None:
    """Opt-in, scoped, conditional — and when it holds, nobody is interrupted."""
    waiter = ImmediateDecision(service=approvals)
    evaluator = ConditionEvaluator(
        allow_list=AllowList(
            entries=[
                AllowListEntry(
                    capability="scale_workload",
                    team_node_id=TEAM,
                    environments=(STAGING,),
                    conditions=(TargetPattern(pattern="checkout-*"),),
                )
            ]
        )
    )
    gate = _gate(requests, executor, clock, waiter=waiter, evaluator=evaluator)

    outcome = await gate.decide(an_action())

    assert outcome.permitted
    assert outcome.autonomous
    assert outcome.approval_id == ""
    assert waiter.waited == [], "a human was asked about an allow-listed action"
    assert plane.was_applied


async def test_an_allow_listed_action_whose_conditions_lapsed_asks_a_human_instead(
    requests, executor, approvals, plane, an_action, clock
) -> None:
    """Not permitted is not the same as not allowed at all.

    The entry exists and its conditions do not hold, which is a refusal with a
    reason an operator can act on — and the reason names the condition.
    """
    waiter = ImmediateDecision(service=approvals)
    evaluator = ConditionEvaluator(
        allow_list=AllowList(
            entries=[
                AllowListEntry(
                    capability="scale_workload",
                    team_node_id=TEAM,
                    environments=(STAGING,),
                    conditions=(TargetPattern(pattern="staging-*"),),
                )
            ]
        )
    )
    gate = _gate(requests, executor, clock, waiter=waiter, evaluator=evaluator)

    outcome = await gate.decide(an_action())

    assert not outcome.permitted
    assert not plane.was_applied
    assert "staging-*" in outcome.reason


async def test_an_unknown_blast_radius_fails_a_maximum_blast_radius_condition(
    registry, plans, executor, approvals, plane, an_action, clock
) -> None:
    """Autonomy is not granted on the strength of a graph extension nobody installed.

    The builder here has nowhere to ask, so the radius is unknown — and unknown
    has to fail a ceiling rather than pass it. The alternative is an allow-list
    that widens itself the day the graph goes down.
    """
    from platform.remediation.autonomy.allow_list import MaximumBlastRadius

    requests = RequestBuilder(registry=registry, plans=plans, approvals=approvals, clock=clock)
    evaluator = ConditionEvaluator(
        allow_list=AllowList(
            entries=[
                AllowListEntry(
                    capability="scale_workload",
                    team_node_id=TEAM,
                    environments=(STAGING,),
                    conditions=(MaximumBlastRadius(limit=100),),
                )
            ]
        )
    )
    gate = _gate(
        requests,
        executor,
        clock,
        waiter=ImmediateDecision(service=approvals),
        evaluator=evaluator,
    )

    outcome = await gate.decide(an_action())

    assert not outcome.permitted
    assert not plane.was_applied
    assert "above the permitted 100" in outcome.reason


# --- Conflicts ---------------------------------------------------------------


async def test_a_second_action_on_the_same_target_is_reported_to_the_reviewer(
    requests, an_action, clock
) -> None:
    """Two mitigations for one workload is normal; deciding the second blind is not."""
    await requests.queue(an_action(action_id="action-1"))

    second = await requests.build(an_action(action_id="action-2"))

    assert second.conflicting, "the second request did not know about the first"
    assert "already pending on this target" in second.rationale()


async def test_approving_one_action_conflicts_the_other_on_the_same_target(
    requests, approvals, an_action, clock
) -> None:
    """Feature 015's sibling conflicting applies to remediations too.

    Each sibling was proposed against state the approval has just replaced, and
    its author is entitled to re-review it against what the target says now.
    """
    first = await requests.queue(an_action(action_id="action-1"))
    second = await requests.queue(an_action(action_id="action-2"))

    await approvals.decide(
        first.change_id,
        approver=_a_principal(REVIEWER),
        permissions=_held_by(REVIEWER, Role.RESPONDER),
        approve=True,
    )

    reloaded = await approvals.get(second.change_id)
    assert reloaded.state is ChangeState.CONFLICTED
