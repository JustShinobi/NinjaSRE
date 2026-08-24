"""Approving a remediation carries it out, and every other verdict carries nothing.

Deciding used to be the whole of what this route did. It recorded the verdict,
the decider and the instant, and said so in its own docstring: the capability the
approval names is never invoked. That left the proposal a note nobody could
answer — a person could say yes and nothing happened, which is a worse product
than one that never asked.

What it must not become is a second way to execute. The approval is carried out
through the gate, which re-reads the emergency stop and the closed loop's guards
before descending the same execution path the loop's own proposals take. A route
that called the executor would be the second entrance the whole design exists to
make impossible, and a structural test elsewhere fails the build over it.

The order is the specification and it is the one that survives a crash between
the two halves. The decision is written first: a recorded approval that did not
run is something an operator finds and re-runs, while a change applied with
nothing saying who authorised it is indistinguishable from a compromise.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from httpx import AsyncClient

from capabilities.tools.remediation import control_plane
from capabilities.tools.remediation.control_plane import ControlPlaneState
from gateway.http.remediation import compose_remediation
from platform.identity.permissions import Role
from platform.persistence.ports import TenantScope
from platform.remediation.models import (
    RemediationAction,
    RemediationTarget,
    StateSnapshot,
    SubTargetResult,
)
from tests.unit.gateway.http.conftest import ORG, TEAM_PAYMENTS, Deployment, issue_token

pytestmark = pytest.mark.unit

PROXY = "http://127.0.0.1:8787"
SCALE = "scale_workload"


class _Plane:
    """Reads a replica count and records every change it is asked to make."""

    def __init__(self) -> None:
        self.changes: list[RemediationAction] = []

    async def read(self, action: RemediationAction) -> ControlPlaneState | None:
        del action
        return ControlPlaneState(values={"replicas": 2}, sub_targets=("checkout",))

    async def change(
        self,
        action: RemediationAction,
        *,
        desired: Mapping[str, Any],
        before: StateSnapshot,
    ) -> tuple[SubTargetResult, ...]:
        del desired, before
        self.changes.append(action)
        return (SubTargetResult(identifier="checkout", changed=True),)


@pytest.fixture
def plane() -> Any:
    bound = _Plane()
    previous = control_plane.bind(bound)
    yield bound
    control_plane.restore(previous)


def _action() -> RemediationAction:
    """Return the write a finished investigation would have proposed."""
    from core.capability.metadata import SideEffectLevel

    return RemediationAction(
        action_id="action-1",
        capability=SCALE,
        target=RemediationTarget(
            identifier="checkout", environment="production", node_id=TEAM_PAYMENTS
        ),
        side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
        requester="ana",
        intent="checkout is saturating its replicas",
        arguments={"workload": "checkout", "environment": "production", "replicas": 4},
        run_id="run-1",
        team_node_id=TEAM_PAYMENTS,
        risk_class="low",
        rollback_planned=True,
    )


async def _queued(deployment: Deployment) -> tuple[str, Any]:
    """Queue one remediation the way the gate does, and return its identifier."""
    desk = await compose_remediation(deployment.state, org_id=ORG, proxy_url=PROXY)
    assert desk is not None, "the test deployment could not compose a remediation desk"
    request = await desk.requests.queue(_action())
    assert request.change_id
    return request.change_id, desk


async def _decide(
    client: AsyncClient,
    deployment: Deployment,
    approval_id: str,
    *,
    verdict: str,
    reason: str = "",
) -> Any:
    secret = await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="reviewer",
        role=Role.OPERATOR,
        node_id=TEAM_PAYMENTS,
    )
    return await client.post(
        f"/v1/approvals/{approval_id}/decision",
        json={"verdict": verdict, "reason": reason},
        headers={"Authorization": f"Bearer {secret}"},
    )


async def _outcome_for(deployment: Deployment) -> Any:
    """Return what the ledger recorded for the action this suite proposes."""
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        return await uow.remediation.get("action-1")


async def test_approving_carries_the_action_out(
    plane: _Plane, deployment: Deployment, client: AsyncClient
) -> None:
    approval_id, _ = await _queued(deployment)

    response = await _decide(client, deployment, approval_id, verdict="approve")

    assert response.status_code == 200, response.text
    assert plane.changes, (
        "a person approved the change and nothing was carried out. The proposal is "
        "a note nobody can answer."
    )
    assert plane.changes[0].capability == SCALE


async def test_the_recorded_outcome_names_the_approval_that_authorised_it(
    plane: _Plane, deployment: Deployment, client: AsyncClient
) -> None:
    approval_id, _ = await _queued(deployment)

    await _decide(client, deployment, approval_id, verdict="approve")

    recorded = await _outcome_for(deployment)
    assert recorded is not None, "the execution left nothing in the outcome ledger"
    assert not recorded.autonomous, (
        "an approved execution was recorded as autonomous. Whether a person decided "
        "is the fact the record exists to carry."
    )
    assert recorded.plan_id, (
        "the obligation to find out whether this worked was written without the plan "
        "that would undo it, so nothing could reverse a change that made things worse."
    )

    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        audited = await uow.audit.query(limit=50)
    details = [event.detail for event in audited if event.detail.get("approval_id") == approval_id]
    assert details, (
        f"no audit row names {approval_id!r} as what authorised the change, so nothing "
        f"ties it to the person who allowed it."
    )
    assert any(detail.get("autonomous") is False for detail in details)


async def test_the_undo_was_stored_before_the_change_happened(
    plane: _Plane, deployment: Deployment, client: AsyncClient
) -> None:
    """Queued, not written on the way out: a plan produced after a failure is a
    plan written under pressure with incomplete information."""
    approval_id, _ = await _queued(deployment)

    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        before = await uow.approvals.rollback_plan_for(approval_id)
    assert before is not None and before.steps

    await _decide(client, deployment, approval_id, verdict="approve")

    assert plane.changes


async def test_rejecting_carries_nothing_out_and_keeps_the_reason(
    plane: _Plane, deployment: Deployment, client: AsyncClient
) -> None:
    approval_id, _ = await _queued(deployment)

    response = await _decide(
        client,
        deployment,
        approval_id,
        verdict="reject",
        reason="the replica count is not the cause; the pod is being OOM killed",
    )

    assert response.status_code == 200, response.text
    assert plane.changes == [], "a rejected change was carried out anyway"
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        decided = await uow.approvals.get_request(approval_id)
    assert decided is not None
    assert decided.reason and "OOM" in decided.reason


async def test_the_switch_engaged_after_the_decision_refuses_the_execution(
    plane: _Plane, deployment: Deployment, client: AsyncClient
) -> None:
    """The case the re-check exists for: an approval granted before somebody
    reached for the stop is exactly the one it has to catch."""
    approval_id, _ = await _queued(deployment)
    deployment.state.kill_switch.engage(engaged_by="ana", reason="the cluster is being drained")

    response = await _decide(client, deployment, approval_id, verdict="approve")

    assert response.status_code == 200, response.text
    assert plane.changes == [], (
        "the emergency stop was engaged between the approval and the execution and "
        "the change went ahead. No autonomy level and no approval overrides it."
    )


async def test_a_deployment_with_no_desk_records_the_decision_and_carries_nothing(
    deployment: Deployment, client: AsyncClient
) -> None:
    """Composed nothing still decides; what it cannot do is act, and that is honest."""
    previous = control_plane.bind(_Plane())
    try:
        approval_id, _ = await _queued(deployment)
    finally:
        control_plane.restore(previous)

    deployment.state.remediation = None
    response = await _decide(client, deployment, approval_id, verdict="approve")

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "approved"
