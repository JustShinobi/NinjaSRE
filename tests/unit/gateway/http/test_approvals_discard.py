"""Discarding an expired decision: `POST /v1/approvals/{approval_id}/discard`.

A transition, never a deletion — `discarded` joins `pending`, `approved`,
`rejected`, `expired` as a fifth `ApprovalState`. The row count in the store
never falls; discarding only ever changes what `state` says.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from capabilities.tools.remediation import control_plane
from capabilities.tools.remediation.control_plane import ControlPlaneState
from core.capability.metadata import SideEffectLevel
from gateway.http.remediation import compose_remediation
from platform.identity.permissions import Role
from platform.persistence.ports import TenantScope
from platform.remediation.models import RemediationAction, RemediationTarget, SubTargetResult
from tests.unit.gateway.http.conftest import ORG, TEAM_PAYMENTS, Deployment, issue_token

pytestmark = pytest.mark.unit

PROXY = "http://127.0.0.1:8787"
SCALE = "scale_workload"


class _Plane:
    async def read(self, action: RemediationAction) -> ControlPlaneState | None:
        del action
        return ControlPlaneState(values={"replicas": 2}, sub_targets=("checkout",))

    async def change(self, action, *, desired, before):  # noqa: ANN001
        del action, desired, before
        return (SubTargetResult(identifier="checkout", changed=True),)


@pytest.fixture
def plane() -> Any:
    bound = _Plane()
    previous = control_plane.bind(bound)
    yield bound
    control_plane.restore(previous)


def _action(*, action_id: str = "action-1") -> RemediationAction:
    return RemediationAction(
        action_id=action_id,
        capability=SCALE,
        target=RemediationTarget(
            identifier="checkout", environment="production", node_id=TEAM_PAYMENTS
        ),
        side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
        requester="ana",
        arguments={"workload": "checkout", "environment": "production", "replicas": 4},
        run_id="run-1",
        team_node_id=TEAM_PAYMENTS,
        rollback_planned=True,
    )


async def _token(deployment: Deployment) -> str:
    return await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="reviewer",
        role=Role.OPERATOR,
        node_id=TEAM_PAYMENTS,
    )


async def _expired(plane: _Plane, deployment: Deployment) -> str:
    desk = await compose_remediation(deployment.state, org_id=ORG, proxy_url=PROXY)
    assert desk is not None
    request = await desk.requests.queue(_action())
    far_future = datetime.now(UTC) + timedelta(days=3650)
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.approvals.expire_due(far_future)
    return request.change_id


async def _row_count(deployment: Deployment) -> int:
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        pending = await uow.approvals.list_pending(limit=1000)
        decided = await uow.approvals.list_decided(limit=1000)
    return len(pending) + len(decided)


async def test_discarding_an_expired_decision_moves_it_to_discarded_with_the_author(
    plane: _Plane, deployment: Deployment, client: AsyncClient
) -> None:
    expired_id = await _expired(plane, deployment)
    before = await _row_count(deployment)
    secret = await _token(deployment)

    response = await client.post(
        f"/v1/approvals/{expired_id}/discard", headers={"Authorization": f"Bearer {secret}"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "discarded"
    assert body.get("decided_by") or body.get("discarded_by")

    after = await _row_count(deployment)
    assert after == before, "discarding must mark a row, never remove one"


async def test_a_discarded_decision_leaves_pending_and_appears_in_decided(
    plane: _Plane, deployment: Deployment, client: AsyncClient
) -> None:
    expired_id = await _expired(plane, deployment)
    secret = await _token(deployment)
    await client.post(
        f"/v1/approvals/{expired_id}/discard", headers={"Authorization": f"Bearer {secret}"}
    )

    pending = await client.get(
        "/v1/approvals", params={"state": "pending"}, headers={"Authorization": f"Bearer {secret}"}
    )
    assert expired_id not in {r["approval_id"] for r in pending.json()["approvals"]}

    decided = await client.get(
        "/v1/approvals", params={"state": "decided"}, headers={"Authorization": f"Bearer {secret}"}
    )
    decided_ids = {r["approval_id"] for r in decided.json()["approvals"]}
    assert expired_id in decided_ids
    matched = next(r for r in decided.json()["approvals"] if r["approval_id"] == expired_id)
    assert matched["verdict"] == "discarded"
