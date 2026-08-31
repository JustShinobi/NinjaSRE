"""Reproposing an expired decision: `POST /v1/approvals/{approval_id}/repropose`.

The mechanism is `RequestBuilder.queue()` (`platform/remediation/request.py`),
called directly — the same one `RemediationGate._through_approval` reaches
through, and the same one `test_approval_execution.py`'s own `_queued` helper
uses to set fixtures up. **Never `RemediationGate.decide()`/`.execute_approved()`**:
that path can suspend waiting for a decision or, under an autonomy policy,
execute the action outright — both wrong for a handler whose whole contract is
"always exactly one new pending proposal, never a write". Calling `queue()`
directly is what makes propose-only structural here rather than a convention
a policy could override.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from capabilities.tools.remediation import control_plane
from capabilities.tools.remediation.control_plane import ControlPlaneState
from core.capability.metadata import SideEffectLevel
from gateway.http.remediation import RemediationDesk, compose_remediation
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
        intent="checkout is saturating its replicas",
        arguments={"workload": "checkout", "environment": "production", "replicas": 4},
        run_id="run-1",
        team_node_id=TEAM_PAYMENTS,
        risk_class="low",
        rollback_planned=True,
    )


async def _desk(deployment: Deployment) -> RemediationDesk:
    desk = await compose_remediation(deployment.state, org_id=ORG, proxy_url=PROXY)
    assert desk is not None, "the test deployment could not compose a remediation desk"
    return desk


async def _token(deployment: Deployment) -> str:
    return await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="reviewer",
        role=Role.OPERATOR,
        node_id=TEAM_PAYMENTS,
    )


async def _expired(plane: _Plane, deployment: Deployment, *, action_id: str = "action-1") -> str:
    """Queue one approval and sweep it past its own window. Returns its id."""
    desk = await _desk(deployment)
    request = await desk.requests.queue(_action(action_id=action_id))
    far_future = datetime.now(UTC) + timedelta(days=3650)
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.approvals.expire_due(far_future)
    return request.change_id


async def _repropose(client: AsyncClient, deployment: Deployment, approval_id: str) -> Any:
    secret = await _token(deployment)
    return await client.post(
        f"/v1/approvals/{approval_id}/repropose", headers={"Authorization": f"Bearer {secret}"}
    )


async def test_reproposing_an_expired_decision_returns_201_with_a_new_pending_one(
    plane: _Plane, deployment: Deployment, client: AsyncClient
) -> None:
    expired_id = await _expired(plane, deployment)

    response = await _repropose(client, deployment, expired_id)

    assert response.status_code == 201, response.text
    new_id = response.json()["approval_id"]
    assert new_id != "" and new_id != expired_id

    secret = await _token(deployment)
    fetched = await client.get(
        f"/v1/approvals/{new_id}", headers={"Authorization": f"Bearer {secret}"}
    )
    assert fetched.status_code == 200
    assert fetched.json()["state"] == "pending"


async def test_the_new_proposal_created_at_is_after_the_expired_ones(
    plane: _Plane, deployment: Deployment, client: AsyncClient
) -> None:
    expired_id = await _expired(plane, deployment)
    secret = await _token(deployment)
    original = (
        await client.get(
            f"/v1/approvals/{expired_id}", headers={"Authorization": f"Bearer {secret}"}
        )
    ).json()

    response = await _repropose(client, deployment, expired_id)
    new_id = response.json()["approval_id"]
    fresh = (
        await client.get(f"/v1/approvals/{new_id}", headers={"Authorization": f"Bearer {secret}"})
    ).json()

    assert fresh["created_at"] > original["created_at"]


async def test_reproposing_the_same_expired_decision_twice_is_idempotent(
    plane: _Plane, deployment: Deployment, client: AsyncClient
) -> None:
    expired_id = await _expired(plane, deployment)

    first = await _repropose(client, deployment, expired_id)
    assert first.status_code == 201

    second = await _repropose(client, deployment, expired_id)
    assert second.status_code == 409, second.text
    assert (
        second.json().get("approval_id", second.text) == first.json()["approval_id"]
        or str(first.json()["approval_id"]) in second.text
    )


async def test_reproposing_a_pending_not_yet_expired_decision_is_refused(
    plane: _Plane, deployment: Deployment, client: AsyncClient
) -> None:
    desk = await _desk(deployment)
    request = await desk.requests.queue(_action())

    response = await _repropose(client, deployment, request.change_id)

    assert response.status_code in (400, 409, 422), response.text


async def test_reproposing_an_expired_decision_whose_capability_no_longer_exists_is_a_named_422(
    plane: _Plane, deployment: Deployment, client: AsyncClient
) -> None:
    """FR-016: an origin that no longer resolves is refused by name, never a
    500. Queued while the capability is registered, exactly like a real
    remediation is; reproposed after the registry drops it, simulating a
    capability retired between the two — `RequestBuilder.build()` re-reads
    the registry on every call, including a repropose's, so this is what
    "the origin no longer resolves" means in practice, not a fixture
    artefact."""
    expired_id = await _expired(plane, deployment)

    desk = await compose_remediation(deployment.state, org_id=ORG, proxy_url=PROXY)
    assert desk is not None
    from platform.remediation.components import ComponentRegistry

    desk.requests.registry = ComponentRegistry()  # nothing registered any more

    response = await _repropose(client, deployment, expired_id)

    assert response.status_code == 422, response.text
    assert SCALE in response.text or "capability" in response.text.lower()
