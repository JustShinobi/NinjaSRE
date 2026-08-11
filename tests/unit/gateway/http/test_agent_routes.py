"""The agent's own description over HTTP, and what it must never carry.

The interesting assertion is the negative one. Article VI says a deployment
chooses what each role runs on, so a route describing the pipeline may name a
*role* and may never name a provider or a model — a surface built on one that
did would present one deployment's choice as the shape of the software.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from config.constants.config_service import MODEL_ROLES
from config.constants.llm import DEFAULT_MODEL_ID, SUPPORTED_PROVIDERS
from core.state.types import STAGE_ORDER
from gateway.http.app import create_app
from gateway.http.state import GatewayState
from platform.identity.permissions import Role
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import ConfigNode, ConfigNodeKind, TenantScope
from tests.unit.gateway.http.conftest import (
    ORG,
    TEAM_PAYMENTS,
    FakeInvestigationRunner,
    issue_token,
)

pytestmark = pytest.mark.asyncio

PIPELINE = "/v1/agent/pipeline"


@pytest.fixture
async def deployment() -> AsyncIterator[tuple[AsyncClient, str]]:
    """Yield a client and a bearer token for somebody who may read a run."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    async with store.begin(TenantScope(org_id=ORG)) as uow:
        await uow.config.upsert(
            ConfigNode(
                node_id=TEAM_PAYMENTS,
                kind=ConfigNodeKind.TEAM,
                name=TEAM_PAYMENTS,
                parent_id=ORG,
            )
        )
    state = GatewayState(
        gateway=store, tokens=TokenService(gateway=store), investigator=FakeInvestigationRunner()
    )
    secret = await issue_token(
        store, state.tokens, user_id="ada", role=Role.RESPONDER, node_id=TEAM_PAYMENTS
    )
    app = create_app(state)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://deployment"
    ) as client:
        yield client, secret


def bearer(secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}"}


async def test_the_stages_come_back_in_the_order_the_pipeline_runs_them(
    deployment: tuple[AsyncClient, str],
) -> None:
    client, secret = deployment
    answer = await client.get(PIPELINE, headers=bearer(secret))
    assert answer.status_code == 200
    body = answer.json()
    assert [stage["name"] for stage in body["stages"]] == [name.value for name in STAGE_ORDER]
    assert [stage["order"] for stage in body["stages"]] == list(range(len(STAGE_ORDER)))


async def test_every_stage_says_what_it_consults_and_what_it_may_change(
    deployment: tuple[AsyncClient, str],
) -> None:
    client, secret = deployment
    body = (await client.get(PIPELINE, headers=bearer(secret))).json()
    for stage in body["stages"]:
        assert stage["summary"]
        assert stage["consults"]
        assert stage["writes"]


async def test_no_provider_and_no_model_identifier_leaves_this_route(
    deployment: tuple[AsyncClient, str],
) -> None:
    client, secret = deployment
    raw = (await client.get(PIPELINE, headers=bearer(secret))).text
    for provider in SUPPORTED_PROVIDERS:
        assert provider not in raw, f"the pipeline named the provider {provider!r}"
    assert DEFAULT_MODEL_ID not in raw


async def test_a_stage_names_a_role_the_configuration_can_bind(
    deployment: tuple[AsyncClient, str],
) -> None:
    client, secret = deployment
    body = (await client.get(PIPELINE, headers=bearer(secret))).json()
    assert body["model_roles"] == list(MODEL_ROLES)
    for stage in body["stages"]:
        assert stage["model_role"] == "" or stage["model_role"] in MODEL_ROLES


async def test_reading_it_needs_a_credential(deployment: tuple[AsyncClient, str]) -> None:
    client, _ = deployment
    assert (await client.get(PIPELINE)).status_code == 400
