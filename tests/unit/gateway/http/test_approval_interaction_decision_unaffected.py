"""T014 — characterisation: deciding by open interaction is untouched.

`console/src/surfaces/decision.tsx`'s `DecisionControls` posts to
`POST /v1/interactions/{interaction_id}/approve|reject`
(`gateway/http/routes/interactions.py`) — a mechanism this feature does not
touch at all: no import, no shared helper, no shared model between that
route and `gateway/http/routes/approvals.py`. This test exists because
nothing in the repository already exercised the route end to end (codegraph's
own blast radius reported no covering test for it before this feature), and
"the feature does not change this" is a claim this suite can hold precisely
because it must pass identically before this feature's implementation lands
and after.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from config.constants.runs import RUN_METADATA_TEAM
from core.agent.interaction.models import ApprovalInteraction, InteractionState
from platform.identity.permissions import Role
from platform.persistence.ports import TenantScope
from platform.persistence.ports.run_trace_store import AgentRun
from tests.unit.gateway.http.conftest import ORG, TEAM_PAYMENTS, Deployment, issue_token

pytestmark = pytest.mark.unit


def _open_approval_interaction(run_id: str) -> ApprovalInteraction:
    now = datetime.now(UTC)
    return ApprovalInteraction(
        interaction_id="int-approve-1",
        run_id=run_id,
        raised_at=now,
        expires_at=now + timedelta(hours=1),
        action="scale_workload",
        summary="Scale checkout to 4 replicas",
    )


async def _seed_run(deployment: Deployment, run_id: str) -> None:
    """The interactions route checks the run's own team against the caller's
    (`gateway/http/routes/tenancy.py::visible`), so a fixture interaction
    needs a real run record behind it — not only an entry in the fake
    investigation runner's own dict."""
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.run_traces.start_run(
            AgentRun(
                run_id=run_id,
                trigger="alert",
                metadata={RUN_METADATA_TEAM: TEAM_PAYMENTS},
            )
        )


async def _reviewer_token(deployment: Deployment) -> str:
    return await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="reviewer",
        role=Role.OPERATOR,
        node_id=TEAM_PAYMENTS,
    )


async def test_approving_by_open_interaction_closes_it_answered(
    deployment: Deployment, client: AsyncClient
) -> None:
    interaction = _open_approval_interaction("run-live-1")
    await _seed_run(deployment, interaction.run_id)
    deployment.runner.interactions[interaction.interaction_id] = interaction
    secret = await _reviewer_token(deployment)

    response = await client.post(
        f"/v1/interactions/{interaction.interaction_id}/approve",
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_open"] is False

    closed = deployment.runner.interactions[interaction.interaction_id]
    assert closed.state is InteractionState.ANSWERED
    assert closed.answer is not None
    assert closed.answer.selected_option == "approve"


async def test_rejecting_by_open_interaction_carries_the_reason(
    deployment: Deployment, client: AsyncClient
) -> None:
    interaction = _open_approval_interaction("run-live-2")
    await _seed_run(deployment, interaction.run_id)
    deployment.runner.interactions[interaction.interaction_id] = interaction
    secret = await _reviewer_token(deployment)

    response = await client.post(
        f"/v1/interactions/{interaction.interaction_id}/reject",
        json={"reason": "the replica count is not the cause"},
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 200, response.text
    closed = deployment.runner.interactions[interaction.interaction_id]
    assert closed.answer is not None
    assert closed.answer.selected_option == "reject"
    assert closed.answer.text == "the replica count is not the cause"
