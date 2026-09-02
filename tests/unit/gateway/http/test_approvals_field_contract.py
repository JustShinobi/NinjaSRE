"""The decision-by-field contract: `GET /v1/approvals` and `GET /v1/approvals/{id}`.

Today the route serves the stored request almost verbatim — `action`,
`summary`, `arguments` — and a console reading it has to interpret the
document itself to answer "what is this, and how risky". This contract adds
the fields a card renders directly: a derived title, a risk score with its
own scale, the steps and the rollback as sentences, the evidence with a
source, the blast radius, the autonomy line, and prior effectiveness. Every
one of them is served — absence is a declared empty value (`""`, `[]`,
`known: false`), never an omitted key, so a client never has to guess whether
a field is missing or was never asked for.

Composed the same way `test_approval_execution.py` already does: a real
`RequestBuilder` from a real `RemediationDesk`, queued directly rather than
through the gate, because a card contract does not care how the approval
arrived — only that the store holds one.
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
from platform.persistence.ports.approval_store import ApprovalRequest
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

#: Every field the plan's Decision 1 shape names, at the top level of one
#: decision. Checked as a set so a key silently dropped fails by name.
_TOP_LEVEL_FIELDS = frozenset(
    {
        "approval_id",
        "state",
        "title",
        "requester",
        "origin",
        "category",
        "intent",
        "risk",
        "steps",
        "rollback",
        "evidence",
        "blast_radius",
        "autonomy",
        "prior_effectiveness",
        "created_at",
        "expires_at",
        "decided_at",
        "decided_by",
        "verdict",
        "raw",
    }
)


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


def _action(
    *, action_id: str = "action-1", capability: str = SCALE, operation: str = ""
) -> RemediationAction:
    return RemediationAction(
        action_id=action_id,
        capability=capability,
        target=RemediationTarget(
            identifier="checkout", environment="production", node_id=TEAM_PAYMENTS
        ),
        side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
        requester="ana",
        intent="checkout is saturating its replicas",
        arguments={"workload": "checkout", "environment": "production", "replicas": 4},
        evidence=(),
        run_id="run-1",
        team_node_id=TEAM_PAYMENTS,
        risk_class="low",
        rollback_planned=True,
        operation=operation,
    )


async def _desk(deployment: Deployment) -> RemediationDesk:
    desk = await compose_remediation(deployment.state, org_id=ORG, proxy_url=PROXY)
    assert desk is not None, "the test deployment could not compose a remediation desk"
    return desk


async def _viewer_token(deployment: Deployment) -> str:
    return await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="reviewer",
        role=Role.OPERATOR,
        node_id=TEAM_PAYMENTS,
    )


async def _list(client: AsyncClient, deployment: Deployment, *, state: str | None = None) -> Any:
    secret = await _viewer_token(deployment)
    params = {} if state is None else {"state": state}
    response = await client.get(
        "/v1/approvals", params=params, headers={"Authorization": f"Bearer {secret}"}
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _detail(client: AsyncClient, deployment: Deployment, approval_id: str) -> Any:
    secret = await _viewer_token(deployment)
    response = await client.get(
        f"/v1/approvals/{approval_id}", headers={"Authorization": f"Bearer {secret}"}
    )
    assert response.status_code == 200, response.text
    return response.json()


# --- T006: the listing --------------------------------------------------------


async def test_a_pending_approval_carries_every_field_the_shape_names(
    plane: _Plane, deployment: Deployment, client: AsyncClient
) -> None:
    desk = await _desk(deployment)
    await desk.requests.queue(_action())

    body = await _list(client, deployment)
    approvals = body["approvals"]
    assert len(approvals) == 1
    record = approvals[0]

    missing = _TOP_LEVEL_FIELDS - set(record)
    assert not missing, f"the listing omits {missing!r} rather than declaring them absent"

    assert record["state"] == "pending"
    assert record["title"] != ""
    assert record["title"] != SCALE, "the title is the capability name, unread"
    assert record["risk"]["scale"] == 5
    assert 1 <= record["risk"]["score"] <= 5
    assert record["risk"]["class"] != ""
    assert isinstance(record["steps"], list)
    assert isinstance(record["rollback"], list)
    assert isinstance(record["evidence"], list)
    assert record["blast_radius"]["known"] in (True, False)
    assert record["autonomy"]["side_effect_level"] == "write_reversible"
    assert record["autonomy"]["queued"] is True
    assert record["origin"]["run_id"] == "run-1"
    assert record["decided_at"] is None
    assert record["decided_by"] is None
    assert record["verdict"] is None


async def test_the_first_step_does_not_repeat_the_why_sentence(
    plane: _Plane, deployment: Deployment, client: AsyncClient
) -> None:
    """`intent` is the reviewer's "why" — the reason the capability's own
    metadata declares approval is needed. The first step is what the action
    executes. A card that prints the same sentence in both is a card that
    reads as saying one thing twice rather than two things once each."""
    desk = await _desk(deployment)
    await desk.requests.queue(_action())

    record = (await _list(client, deployment))["approvals"][0]
    assert record["intent"] == "checkout is saturating its replicas"
    assert record["steps"], "expected at least one step"
    assert record["steps"][0]["summary"] != record["intent"]
    assert record["steps"][0]["summary"] != ""


async def test_the_first_step_names_the_capability_and_its_own_arguments(
    plane: _Plane, deployment: Deployment, client: AsyncClient
) -> None:
    """Once the why sentence no longer sits in the step, the step still has
    something genuine of its own to show: which capability runs, and against
    which arguments — not a second copy of the justification."""
    desk = await _desk(deployment)
    await desk.requests.queue(
        _action(operation="scale_workload(environment='production', replicas=4)")
    )

    record = (await _list(client, deployment))["approvals"][0]
    step = record["steps"][0]
    assert step["capability"] == SCALE
    assert step["summary"] == "scale_workload(environment='production', replicas=4)"
    assert step["summary"] != record["intent"]


async def test_a_field_the_stored_document_never_named_reads_as_a_declared_absence(
    plane: _Plane, deployment: Deployment, client: AsyncClient
) -> None:
    """`intent`, `evidence`, `prior_effectiveness` are absent from this action's
    own payload where the builder does not fill them — never an omitted key."""
    desk = await _desk(deployment)
    bare = RemediationAction(
        action_id="action-bare",
        capability=SCALE,
        target=RemediationTarget(identifier="checkout", environment="production"),
        side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
        requester="ana",
        arguments={},
    )
    await desk.requests.queue(bare)

    record = (await _list(client, deployment))["approvals"][0]
    assert record["intent"] == ""
    assert record["evidence"] == []
    assert record["prior_effectiveness"]["summary"] == ""


async def test_an_irreversible_row_with_no_plan_is_never_reported_reversible(
    deployment: Deployment, client: AsyncClient
) -> None:
    """This route lists every row the approval store holds, not only the ones a
    remediation desk queued — a configuration edit, a knowledge proposal, the
    agent's own proposal queue and the demo seeder all write there, and none of
    them stores the rollback waiver the autonomy line reads. The reviewer is
    shown "this can be undone" as an assurance; saying it about an irreversible
    action with no plan behind it is the one wrong answer nobody can recover
    from once the button is pressed."""
    now = datetime.now(UTC)
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.approvals.create_request(
            ApprovalRequest(
                approval_id="apr-no-waiver",
                run_id="",
                action="estate.delete_snapshot",
                side_effect_level="write_irreversible",
                summary="Delete the checkout snapshot",
                requested_at=now,
                expires_at=now + timedelta(hours=1),
                arguments={"snapshot": "checkout-2026-08"},
            )
        )

    record = (await _list(client, deployment))["approvals"][0]

    assert record["approval_id"] == "apr-no-waiver"
    assert record["autonomy"]["side_effect_level"] == "write_irreversible"
    assert record["rollback_plan"] is None
    assert record["autonomy"]["reversible"] is False


async def test_an_unrecognised_state_filter_is_refused_rather_than_answered_with_pending(
    deployment: Deployment, client: AsyncClient
) -> None:
    """A misspelled bucket used to fall through to the pending queue with a
    `200`, so a client asking for the expired ones was handed the live ones and
    had nothing in the response saying so. Refusing names the mistake."""
    secret = await _viewer_token(deployment)

    response = await client.get(
        "/v1/approvals",
        params={"state": "expiredd"},
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 422, response.text


async def test_default_listing_excludes_expired_and_decided(
    plane: _Plane, deployment: Deployment, client: AsyncClient
) -> None:
    desk = await _desk(deployment)
    request = await desk.requests.queue(_action())

    # Decide it, so it leaves `pending`.
    secret = await _viewer_token(deployment)
    await client.post(
        f"/v1/approvals/{request.change_id}/decision",
        json={"verdict": "reject", "reason": "not now"},
        headers={"Authorization": f"Bearer {secret}"},
    )

    body = await _list(client, deployment)
    assert body["approvals"] == []


async def test_state_expired_returns_only_truly_lapsed_rows(
    plane: _Plane, deployment: Deployment, client: AsyncClient
) -> None:
    desk = await _desk(deployment)
    lapsed = await desk.requests.queue(_action(action_id="action-lapsed"))

    # A clock far enough forward that the queued request's window has
    # closed — swept the same way `GET /v1/approvals` sweeps before
    # listing (T015), used directly here to set the fixture up rather than
    # reaching into the fake's internals.
    far_future = datetime.now(UTC) + timedelta(days=3650)
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.approvals.expire_due(far_future)

    # Queued after the sweep, so this one's own window is still open.
    fresh = await desk.requests.queue(_action(action_id="action-fresh"))

    expired = await _list(client, deployment, state="expired")
    ids = {record["approval_id"] for record in expired["approvals"]}
    assert lapsed.change_id in ids
    assert fresh.change_id not in ids

    pending = await _list(client, deployment, state="pending")
    pending_ids = {record["approval_id"] for record in pending["approvals"]}
    assert pending_ids == {fresh.change_id}


async def test_state_decided_returns_approved_and_rejected_most_recent_first_with_verdict(
    plane: _Plane, deployment: Deployment, client: AsyncClient
) -> None:
    desk = await _desk(deployment)
    first = await desk.requests.queue(_action(action_id="action-first"))
    second = await desk.requests.queue(_action(action_id="action-second"))

    secret = await _viewer_token(deployment)
    await client.post(
        f"/v1/approvals/{first.change_id}/decision",
        json={"verdict": "approve", "reason": ""},
        headers={"Authorization": f"Bearer {secret}"},
    )
    await client.post(
        f"/v1/approvals/{second.change_id}/decision",
        json={"verdict": "reject", "reason": "not this one"},
        headers={"Authorization": f"Bearer {secret}"},
    )

    decided = await _list(client, deployment, state="decided")
    records = decided["approvals"]
    assert [record["approval_id"] for record in records] == [second.change_id, first.change_id]
    assert records[0]["verdict"] == "rejected"
    assert records[0]["decided_by"] == "reviewer"
    assert records[1]["verdict"] == "approved"


# --- T007: the detail ----------------------------------------------------------


async def test_the_detail_carries_the_same_shape_plus_the_raw_document(
    plane: _Plane, deployment: Deployment, client: AsyncClient
) -> None:
    desk = await _desk(deployment)
    request = await desk.requests.queue(_action())

    record = await _detail(client, deployment, request.change_id)
    missing = _TOP_LEVEL_FIELDS - set(record)
    assert not missing, f"the detail omits {missing!r}"
    assert record["raw"] != {}
    assert SCALE in str(record["raw"])


async def test_the_title_is_identical_between_the_listing_and_the_detail(
    plane: _Plane, deployment: Deployment, client: AsyncClient
) -> None:
    desk = await _desk(deployment)
    request = await desk.requests.queue(_action())

    listed = (await _list(client, deployment))["approvals"][0]
    detail = await _detail(client, deployment, request.change_id)

    assert listed["title"] == detail["title"]
    assert listed["title"] != ""
