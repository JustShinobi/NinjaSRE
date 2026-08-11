"""Granting and revoking a role over HTTP, and the one revocation that is refused.

The last-owner rule is the interesting half. It is evaluated over the whole
organisation rather than over the grant being removed, so handing ownership over
is allowed and removing the last owner is not — and the refusal has to say which
of those happened, because "no" without a reason sends somebody to look for a
permission they already hold.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.http.app import create_app
from gateway.http.state import GatewayState
from platform.identity.permissions import Role
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import ConfigNode, ConfigNodeKind, TenantScope
from platform.persistence.ports.identity_repository import User
from tests.unit.gateway.http.conftest import (
    ORG,
    TEAM_PAYMENTS,
    FakeInvestigationRunner,
    issue_token,
)

GRANTS = "/identity/grants"


@pytest.fixture
async def deployment() -> AsyncIterator[tuple[AsyncClient, FakePersistence, str]]:
    """Yield a client, the store behind it, and an owner's bearer token."""
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
        await uow.identity.upsert_user(
            User(user_id="grace", email="grace@acme.test", display_name="Grace")
        )
    state = GatewayState(
        gateway=store, tokens=TokenService(gateway=store), investigator=FakeInvestigationRunner()
    )
    secret = await issue_token(store, state.tokens, user_id="ada", role=Role.OWNER, node_id=None)
    app = create_app(state)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://deployment"
    ) as client:
        yield client, store, secret


def bearer(secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}"}


async def test_a_role_is_granted_and_reads_back_in_the_listing(
    deployment: tuple[AsyncClient, FakePersistence, str],
) -> None:
    client, _, secret = deployment
    added = await client.post(
        GRANTS,
        json={"principal_id": "grace", "role": "responder", "node_id": TEAM_PAYMENTS},
        headers=bearer(secret),
    )
    assert added.status_code == 201
    grant_id = added.json()["grant_id"]

    listed = (await client.get(GRANTS, headers=bearer(secret))).json()["grants"]
    assert grant_id in {entry["grant_id"] for entry in listed}


async def test_granting_the_same_role_twice_is_one_grant(
    deployment: tuple[AsyncClient, FakePersistence, str],
) -> None:
    client, _, secret = deployment
    body = {"principal_id": "grace", "role": "responder", "node_id": TEAM_PAYMENTS}
    first = await client.post(GRANTS, json=body, headers=bearer(secret))
    second = await client.post(GRANTS, json=body, headers=bearer(secret))
    assert first.json()["grant_id"] == second.json()["grant_id"]

    listed = (await client.get(GRANTS, headers=bearer(secret))).json()["grants"]
    held = [entry for entry in listed if entry["principal_id"] == "grace"]
    assert len(held) == 1


async def test_a_granted_role_is_taken_away_again(
    deployment: tuple[AsyncClient, FakePersistence, str],
) -> None:
    client, _, secret = deployment
    added = await client.post(
        GRANTS,
        json={"principal_id": "grace", "role": "responder", "node_id": TEAM_PAYMENTS},
        headers=bearer(secret),
    )
    grant_id = added.json()["grant_id"]

    removed = await client.delete(f"{GRANTS}/{grant_id}", headers=bearer(secret))
    assert removed.status_code == 200
    assert removed.json()["role"] == "responder"

    listed = (await client.get(GRANTS, headers=bearer(secret))).json()["grants"]
    assert grant_id not in {entry["grant_id"] for entry in listed}


async def test_removing_the_last_owner_is_refused_with_its_own_message(
    deployment: tuple[AsyncClient, FakePersistence, str],
) -> None:
    client, _, secret = deployment
    listed = (await client.get(GRANTS, headers=bearer(secret))).json()["grants"]
    owner = next(entry for entry in listed if entry["role"] == "owner")

    refused = await client.delete(f"{GRANTS}/{owner['grant_id']}", headers=bearer(secret))
    assert refused.status_code == 409
    assert "no owner" in refused.json()["error"]["message"]


async def test_ownership_can_be_handed_over_by_granting_first(
    deployment: tuple[AsyncClient, FakePersistence, str],
) -> None:
    client, _, secret = deployment
    granted = await client.post(
        GRANTS,
        json={"principal_id": "grace", "role": "owner"},
        headers=bearer(secret),
    )
    assert granted.status_code == 201

    listed = (await client.get(GRANTS, headers=bearer(secret))).json()["grants"]
    previous = next(
        entry for entry in listed if entry["role"] == "owner" and entry["principal_id"] == "ada"
    )
    assert (
        await client.delete(f"{GRANTS}/{previous['grant_id']}", headers=bearer(secret))
    ).status_code == 200


async def test_a_role_this_deployment_does_not_have_is_refused_naming_the_ones_it_does(
    deployment: tuple[AsyncClient, FakePersistence, str],
) -> None:
    client, _, secret = deployment
    refused = await client.post(
        GRANTS,
        json={"principal_id": "grace", "role": "sorcerer"},
        headers=bearer(secret),
    )
    assert refused.status_code == 400
    assert "owner" in refused.json()["error"]["message"]


async def test_granting_to_a_principal_nobody_created_is_not_found(
    deployment: tuple[AsyncClient, FakePersistence, str],
) -> None:
    client, _, secret = deployment
    refused = await client.post(
        GRANTS,
        json={"principal_id": "nobody", "role": "viewer"},
        headers=bearer(secret),
    )
    assert refused.status_code == 404


async def test_a_grant_and_a_revocation_each_leave_an_audit_row(
    deployment: tuple[AsyncClient, FakePersistence, str],
) -> None:
    client, store, secret = deployment
    added = await client.post(
        GRANTS,
        json={"principal_id": "grace", "role": "viewer", "node_id": TEAM_PAYMENTS},
        headers=bearer(secret),
    )
    await client.delete(f"{GRANTS}/{added.json()['grant_id']}", headers=bearer(secret))

    async with store.begin(TenantScope(org_id=ORG)) as uow:
        events = await uow.audit.query()
    actions = [event.action for event in events]
    assert "permission.grant" in actions
    assert "permission.revoke" in actions


async def test_a_viewer_may_not_grant_a_role(
    deployment: tuple[AsyncClient, FakePersistence, str],
) -> None:
    client, store, _ = deployment
    tokens = TokenService(gateway=store)
    viewer = await issue_token(
        store, tokens, user_id="vic", role=Role.VIEWER, node_id=TEAM_PAYMENTS
    )
    refused = await client.post(
        GRANTS,
        json={"principal_id": "grace", "role": "owner"},
        headers=bearer(viewer),
    )
    assert refused.status_code == 403
