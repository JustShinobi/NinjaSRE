"""The episode one investigation left behind, addressed by that investigation.

The board calls this the return leg, and names it the one nobody built: the
eighth firing of a subject the corpus already has a strategy for should not cost
what the first did. The card that reads an investigation could not close that
loop, because nothing let it ask "what did this run teach" — only "what does the
whole corpus hold", which is a different question with a different size.

``EpisodeStore.get_by_run`` has answered it all along. What was missing was a
way to ask over the API, and the console filtering a corpus search down to one
run in a browser would be the same read at the wrong layer: fine at fifty
episodes, wrong at the size the corpus becomes worth having.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from platform.identity.permissions import Role
from platform.persistence.ports.episode_store import Episode, EpisodeOutcome
from platform.persistence.ports.transaction import TenantScope
from tests.unit.gateway.http.conftest import ORG, TEAM_PAYMENTS, Deployment, issue_token

pytestmark = pytest.mark.anyio

WRITTEN_AT = datetime(2026, 8, 26, 22, 41, tzinfo=UTC)


async def _owner(deployment: Deployment) -> dict[str, str]:
    secret = await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="ana",
        role=Role.OWNER,
        node_id=ORG,
    )
    return {"authorization": f"Bearer {secret}"}


async def _write_episode(deployment: Deployment, *, run_id: str) -> None:
    scope = TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)
    async with deployment.gateway.begin(scope) as uow:
        await uow.episodes.save(
            Episode(
                episode_id="ep-0001",
                title="A guest stopped by hand ends this shape in one call",
                summary="proxmox_guest_tasks carried the task id and the user who ran it.",
                signature="sig-lxc-122",
                outcome=EpisodeOutcome.RESOLVED,
                run_id=run_id,
                occurred_at=WRITTEN_AT,
                components=("lxc/122", "pve01"),
            )
        )


async def test_a_run_that_taught_something_says_what(
    client: AsyncClient, deployment: Deployment
) -> None:
    await _write_episode(deployment, run_id="run-0001")

    response = await client.get(
        "/v1/memory/episode", params={"run_id": "run-0001"}, headers=await _owner(deployment)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["episode"]["episode_id"] == "ep-0001"
    assert body["episode"]["outcome"] == EpisodeOutcome.RESOLVED.value
    assert "one call" in body["episode"]["title"]


async def test_a_run_that_taught_nothing_is_empty_rather_than_missing(
    client: AsyncClient, deployment: Deployment
) -> None:
    """A run with no episode is an ordinary run, not a bad address.

    404 would make the card's own read an error state, and "this run wrote
    nothing down" is a sentence a section should be able to print calmly.
    """
    response = await client.get(
        "/v1/memory/episode", params={"run_id": "run-nothing"}, headers=await _owner(deployment)
    )

    assert response.status_code == 200
    assert response.json()["episode"] is None


async def test_naming_no_run_is_refused_rather_than_answered_at_random(
    client: AsyncClient, deployment: Deployment
) -> None:
    response = await client.get("/v1/memory/episode", headers=await _owner(deployment))

    assert response.status_code == 422


async def test_an_episode_names_the_run_it_came_from(
    client: AsyncClient, deployment: Deployment
) -> None:
    """The link that makes the corpus evidence rather than assertion.

    `screens/memory.tsx` says it in its own words: "each links to the run that
    produced it, which is the property that makes the corpus evidence rather
    than assertion — a claim about what happened in April is worth what the
    transcript behind it is worth." The console builds that link from
    `run_id`, and `EpisodeView` did not carry one, so every row on the Learned
    tab pointed at `/runs/` with nothing after it. Measured on staging: three
    episodes, three dead links.

    Asserted on the search result rather than only on the single-episode read,
    because the list is where the link is drawn.
    """
    await _write_episode(deployment, run_id="run-0001")

    response = await client.get("/v1/memory/search", headers=await _owner(deployment))

    assert response.status_code == 200
    episodes = response.json()["episodes"]
    assert episodes, "the corpus this test just wrote to came back empty"
    assert episodes[0]["run_id"] == "run-0001"
