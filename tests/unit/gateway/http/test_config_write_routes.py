"""Editing configuration over HTTP: the redundant warning, and clearing a field.

Two things a console cannot work out for itself, so both are served.

"You already inherit this" needs the parent's document, which no client holds.
"Clear this and go back to inheriting" needs a way to say *remove* in a request
whose body is otherwise a document to merge — and since no key in a
configuration document is ever a directive, the removal travels beside the patch
rather than inside it.

The audit assertions are here rather than in the service suite on purpose: what
the acceptance asks for is that a write *through the API* leaves a record naming
the actor, the resource and the outcome, and the actor only exists at this
boundary.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from platform.config_service.document import NodeDocument
from platform.identity.permissions import Role
from platform.persistence.ports.config_repository import ConfigNode
from platform.persistence.ports.transaction import TenantScope
from tests.unit.gateway.http.conftest import (
    ORG,
    TEAM_PAYMENTS,
    Deployment,
    issue_token,
)

pytestmark = pytest.mark.anyio


async def _owner(deployment: Deployment) -> dict[str, str]:
    """Return the authorisation header of an organisation-wide owner."""
    secret = await issue_token(
        deployment.gateway, deployment.tokens, user_id="ada", role=Role.OWNER, node_id=None
    )
    return {"authorization": f"Bearer {secret}"}


async def _store(deployment: Deployment, node_id: str, document: NodeDocument) -> None:
    """Put ``document`` on ``node_id``, whatever it held before."""
    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        node = await uow.config.get(node_id)
        assert node is not None
        await uow.config.upsert(
            ConfigNode(
                node_id=node.node_id,
                kind=node.kind,
                name=node.name,
                parent_id=node.parent_id,
                values=document.to_values(),
                version=node.version,
            )
        )


# --- The redundant warning ----------------------------------------------------


async def test_a_preview_names_the_paths_that_would_be_set_to_what_is_inherited(
    client: AsyncClient, deployment: Deployment
) -> None:
    await _store(deployment, ORG, NodeDocument.of({"agents": {"tool_budget": 3}}))

    preview = await client.post(
        f"/v1/config/{TEAM_PAYMENTS}/preview",
        headers=await _owner(deployment),
        json={"patch": {"agents": {"tool_budget": 3}}},
    )

    assert preview.status_code == 200
    assert preview.json()["redundant"] == [
        {"path": "agents.tool_budget", "value": 3, "inherited_from": ORG}
    ]


async def test_a_preview_of_a_value_that_really_moves_reports_nothing_redundant(
    client: AsyncClient, deployment: Deployment
) -> None:
    await _store(deployment, ORG, NodeDocument.of({"agents": {"tool_budget": 3}}))

    preview = await client.post(
        f"/v1/config/{TEAM_PAYMENTS}/preview",
        headers=await _owner(deployment),
        json={"patch": {"agents": {"tool_budget": 9}}},
    )

    assert preview.json()["redundant"] == []


# --- Clearing a field back to inherited ---------------------------------------


async def test_a_preview_of_a_clear_says_what_it_reverts_to_and_from_where(
    client: AsyncClient, deployment: Deployment
) -> None:
    await _store(deployment, ORG, NodeDocument.of({"agents": {"tool_budget": 3}}))
    await _store(deployment, TEAM_PAYMENTS, NodeDocument.of({"agents": {"tool_budget": 9}}))

    preview = await client.post(
        f"/v1/config/{TEAM_PAYMENTS}/preview",
        headers=await _owner(deployment),
        json={"patch": {}, "remove": ["agents.tool_budget"]},
    )

    assert preview.status_code == 200
    body = preview.json()
    assert body["reverts"] == [{"path": "agents.tool_budget", "value": 3, "inherited_from": ORG}]
    assert body["values"]["agents"]["tool_budget"] == 3
    assert body["provenance"]["agents.tool_budget"] == ORG


async def test_clearing_a_field_removes_the_local_value_and_restores_the_inherited_one(
    client: AsyncClient, deployment: Deployment
) -> None:
    await _store(deployment, ORG, NodeDocument.of({"agents": {"tool_budget": 3}}))
    await _store(deployment, TEAM_PAYMENTS, NodeDocument.of({"agents": {"tool_budget": 9}}))
    headers = await _owner(deployment)

    written = await client.put(
        f"/v1/config/{TEAM_PAYMENTS}",
        headers=headers,
        json={"patch": {}, "remove": ["agents.tool_budget"]},
    )

    assert written.status_code == 200
    assert written.json()["values"]["agents"]["tool_budget"] == 3
    assert written.json()["provenance"]["agents.tool_budget"] == ORG


async def test_clearing_is_distinct_from_setting_the_inherited_value(
    client: AsyncClient, deployment: Deployment
) -> None:
    # Both resolve to 3 today. Only one of them still follows the organisation
    # tomorrow, and the provenance is where the difference is legible.
    await _store(deployment, ORG, NodeDocument.of({"agents": {"tool_budget": 3}}))
    await _store(deployment, TEAM_PAYMENTS, NodeDocument.of({"agents": {"tool_budget": 9}}))
    headers = await _owner(deployment)

    matched = await client.put(
        f"/v1/config/{TEAM_PAYMENTS}",
        headers=headers,
        json={"patch": {"agents": {"tool_budget": 3}}},
    )
    assert matched.json()["provenance"]["agents.tool_budget"] == TEAM_PAYMENTS

    cleared = await client.put(
        f"/v1/config/{TEAM_PAYMENTS}",
        headers=headers,
        json={"patch": {}, "remove": ["agents.tool_budget"]},
    )
    assert cleared.json()["provenance"]["agents.tool_budget"] == ORG


# --- The record every write leaves --------------------------------------------


async def test_a_save_through_the_route_is_audited_with_actor_resource_and_outcome(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _owner(deployment)

    await client.put(
        f"/v1/config/{TEAM_PAYMENTS}",
        headers=headers,
        json={"patch": {"agents": {"tool_budget": 6}}},
    )

    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        events = await uow.audit.query()
    written = [
        event
        for event in events
        if event.resource_id == TEAM_PAYMENTS and event.detail.get("field") == "agents.tool_budget"
    ]
    assert len(written) == 1
    assert written[0].actor_id == "ada"
    assert written[0].outcome.value == "allowed"
    assert written[0].detail["new_value"] == 6


async def test_a_clear_through_the_route_is_audited_as_its_own_row(
    client: AsyncClient, deployment: Deployment
) -> None:
    await _store(deployment, TEAM_PAYMENTS, NodeDocument.of({"agents": {"tool_budget": 9}}))

    await client.put(
        f"/v1/config/{TEAM_PAYMENTS}",
        headers=await _owner(deployment),
        json={"patch": {}, "remove": ["agents.tool_budget"]},
    )

    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        events = await uow.audit.query()
    cleared = [
        event
        for event in events
        if event.resource_id == TEAM_PAYMENTS and event.detail.get("field") == "agents.tool_budget"
    ]
    assert len(cleared) == 1
    assert cleared[0].detail["previous_value"] == 9
    assert cleared[0].detail["new_value"] is None
