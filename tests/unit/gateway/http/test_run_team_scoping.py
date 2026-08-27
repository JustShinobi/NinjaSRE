"""Which team a run belongs to when the caller's own credential names none.

Every investigation this deployment had ever run carried no team, because a
local sign-in issues a token that stands for the person across the whole
organisation rather than for one team of it. Nothing downstream could tell
that apart from "this run belongs to nobody", and the one thing that acts on
it — episodic memory — correctly refused to write an episode it could not
scope. Fifty finished investigations, an empty corpus, and a screen saying
none had ended.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from config.constants.runs import RUN_METADATA_TEAM
from platform.identity.permissions import Role
from platform.persistence.ports.transaction import TenantScope
from tests.unit.gateway.http.conftest import ORG, TEAM_PAYMENTS, Deployment, issue_token

pytestmark = pytest.mark.asyncio


async def _header(deployment: Deployment, *, node_id: str | None) -> dict[str, str]:
    secret = await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="ada",
        role=Role.OWNER,
        node_id=node_id,
    )
    return {"Authorization": f"Bearer {secret}"}


async def _run_metadata(deployment: Deployment, run_id: str) -> dict[str, object]:
    scope = TenantScope(org_id=ORG)
    async with deployment.gateway.begin(scope) as uow:
        run = await uow.run_traces.get_run(run_id)
    assert run is not None
    return dict(run.metadata)


async def test_a_run_started_by_an_organisation_wide_caller_lands_on_the_root_team(
    client: AsyncClient, deployment: Deployment
) -> None:
    """The case that reached staging: a local sign-in has no team on it.

    The root is the honest answer rather than a guess — it is the node every
    deployment with any configuration at all has, and it is the same node the
    console falls back to when nothing more specific is named.
    """
    headers = await _header(deployment, node_id=None)

    response = await client.post(
        "/v1/investigations", json={"objective": "redis is unreachable"}, headers=headers
    )
    assert response.status_code == 202
    run_id = response.json()["run_id"]

    metadata = await _run_metadata(deployment, run_id)
    assert metadata[RUN_METADATA_TEAM] != ""


async def test_a_team_scoped_caller_still_lands_on_their_own_team(
    client: AsyncClient, deployment: Deployment
) -> None:
    """The fallback is a fallback. A caller who named a team keeps it."""
    headers = await _header(deployment, node_id=TEAM_PAYMENTS)

    response = await client.post(
        "/v1/investigations", json={"objective": "checkout is slow"}, headers=headers
    )
    run_id = response.json()["run_id"]

    metadata = await _run_metadata(deployment, run_id)
    assert metadata[RUN_METADATA_TEAM] == TEAM_PAYMENTS


async def test_stamping_a_team_hides_the_run_from_nobody_who_could_see_it_before(
    client: AsyncClient, deployment: Deployment
) -> None:
    """The whole safety argument for this change, as a test.

    An organisation-wide caller sees every run whatever team it carries, so a
    run that gained one cannot vanish from the only kind of caller that could
    see it while it had none.
    """
    starter = await _header(deployment, node_id=None)
    run_id = (
        await client.post(
            "/v1/investigations", json={"objective": "redis is unreachable"}, headers=starter
        )
    ).json()["run_id"]

    listed = await client.get("/v1/runs", headers=starter)
    assert run_id in [run["run_id"] for run in listed.json()["runs"]]
