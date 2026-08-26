"""What each role actually runs on, answered by the deployment that runs it.

The console had no way to ask this, so it derived it — and derived it wrong.
It read the *schema's* default for a role nobody had bound (`ConfigField.default`,
a value in a Pydantic field) and printed `anthropic / claude-sonnet-5` over a
deployment whose every call went to Gemini. Somebody read that panel during an
incident and spent an afternoon looking for a missing Anthropic credential.

The rule the deployment follows is one function — ``resolve_binding`` — and it
has three answers, not two: this role was chosen, this role follows the
investigator, or nothing is configured anywhere. A console holding only a
provider string cannot tell them apart, which is the whole reason it guessed.
So the deployment publishes its own resolution and the console renders it.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from config.constants.config_service import (
    MODEL_ROLE_EXTRACTION,
    MODEL_ROLE_INVESTIGATOR,
    MODEL_ROLES,
)
from core.llm.factory import publish_configured_bindings, reset_configured_bindings
from platform.identity.permissions import Role
from tests.unit.gateway.http.conftest import ORG, Deployment, issue_token

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def _forget_published_configuration():
    """The published table is process-wide; leave none of it behind."""
    reset_configured_bindings()
    yield
    reset_configured_bindings()


async def _owner(deployment: Deployment) -> dict[str, str]:
    secret = await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="ana",
        role=Role.OWNER,
        node_id=ORG,
    )
    return {"authorization": f"Bearer {secret}"}


async def test_every_declared_role_is_answered_for(
    client: AsyncClient, deployment: Deployment
) -> None:
    """A role missing from the answer is a role nobody can check."""
    response = await client.get("/v1/models/roles", headers=await _owner(deployment))

    assert response.status_code == 200
    answered = {entry["role"] for entry in response.json()["roles"]}
    assert answered == set(MODEL_ROLES)


async def test_a_role_nobody_bound_says_it_follows_the_investigator(
    client: AsyncClient, deployment: Deployment
) -> None:
    """The reading the console could not get, and guessed at instead."""
    publish_configured_bindings({MODEL_ROLE_INVESTIGATOR: ("google_gemini", "gemini-flash-latest")})

    response = await client.get("/v1/models/roles", headers=await _owner(deployment))

    roles = {entry["role"]: entry for entry in response.json()["roles"]}
    assert roles[MODEL_ROLE_INVESTIGATOR]["source"] == "configured"

    extraction = roles[MODEL_ROLE_EXTRACTION]
    assert extraction["source"] == "investigator"
    assert extraction["provider"] == "google_gemini"
    assert extraction["model"] == "gemini-flash-latest"


async def test_with_nothing_configured_every_role_says_so(
    client: AsyncClient, deployment: Deployment
) -> None:
    """Not "anthropic because the schema says so" — "nobody has chosen"."""
    response = await client.get("/v1/models/roles", headers=await _owner(deployment))

    for entry in response.json()["roles"]:
        assert entry["source"] == "default", entry


async def test_the_answer_is_the_deployment_s_rather_than_a_node_s(
    client: AsyncClient, deployment: Deployment
) -> None:
    """No node in the address, on purpose.

    A model binding is published once, at boot, from the root — nothing
    republishes per team. An endpoint that took a node would promise a
    per-team answer the runtime does not honour, which is the same divergence
    this route exists to close.
    """
    publish_configured_bindings({MODEL_ROLE_INVESTIGATOR: ("google_gemini", "gemini-flash-latest")})
    headers = await _owner(deployment)

    first = await client.get("/v1/models/roles", headers=headers)
    second = await client.get("/v1/models/roles", headers=headers)

    assert first.json() == second.json()
