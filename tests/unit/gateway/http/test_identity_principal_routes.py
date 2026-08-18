"""Creating a person over HTTP: who may, what is stored, and what the audit keeps.

Three properties matter more here than in most routes, because this one mints
an account with a password. The refusal has to be the server's, not the
console's; the password has to reach storage only as a hash, through the same
construction the environment-configured account already uses; and the new
principal has to come away from the call holding no more power than it was
explicitly granted afterwards — this route grants nothing at all.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.http.app import create_app
from gateway.http.state import GatewayState
from platform.identity.break_glass import verify_secret
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

PRINCIPALS = "/identity/principals"
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


async def test_a_principal_is_created_and_reads_back_in_the_listing(
    deployment: tuple[AsyncClient, FakePersistence, str],
) -> None:
    client, _, secret = deployment
    created = await client.post(
        PRINCIPALS,
        json={
            "email": "grace@acme.test",
            "display_name": "Grace",
            "password": "correct-horse-battery",
        },
        headers=bearer(secret),
    )
    assert created.status_code == 201
    body = created.json()
    assert body["email"] == "grace@acme.test"
    assert body["display_name"] == "Grace"
    assert body["kind"] == "user"
    assert body["is_active"] is True
    assert "password" not in body

    listed = (await client.get(PRINCIPALS, headers=bearer(secret))).json()["users"]
    assert body["user_id"] in {entry["user_id"] for entry in listed}


async def test_the_password_is_hashed_through_the_same_scheme_the_local_account_uses(
    deployment: tuple[AsyncClient, FakePersistence, str],
) -> None:
    client, store, secret = deployment
    password = "correct-horse-battery"
    created = (
        await client.post(
            PRINCIPALS,
            json={"email": "grace@acme.test", "display_name": "Grace", "password": password},
            headers=bearer(secret),
        )
    ).json()

    async with store.begin(TenantScope(org_id=ORG)) as uow:
        stored = await uow.identity.get_user(created["user_id"])

    assert stored is not None
    assert stored.local_password_hash is not None
    assert stored.local_password_hash != password
    assert password not in stored.local_password_hash
    assert verify_secret(password, stored.local_password_hash)


async def test_the_created_principal_holds_no_role_until_one_is_granted(
    deployment: tuple[AsyncClient, FakePersistence, str],
) -> None:
    """No escalation: this route mints an account and nothing else.

    Confirmed against the real grants listing rather than inferred, so a
    later change that quietly started binding a role at creation would show
    up here as a grant that exists before anybody asked for one.
    """
    client, _, secret = deployment
    created = (
        await client.post(
            PRINCIPALS,
            json={"email": "grace@acme.test", "display_name": "Grace", "password": "correct-horse"},
            headers=bearer(secret),
        )
    ).json()

    grants = (
        await client.get(
            GRANTS, params={"principal_id": created["user_id"]}, headers=bearer(secret)
        )
    ).json()["grants"]
    assert grants == []


async def test_a_viewer_may_not_create_a_principal(
    deployment: tuple[AsyncClient, FakePersistence, str],
) -> None:
    client, store, _ = deployment
    tokens = TokenService(gateway=store)
    viewer = await issue_token(
        store, tokens, user_id="vic", role=Role.VIEWER, node_id=TEAM_PAYMENTS
    )

    refused = await client.post(
        PRINCIPALS,
        json={"email": "grace@acme.test", "display_name": "Grace", "password": "correct-horse"},
        headers=bearer(viewer),
    )
    assert refused.status_code == 403
    assert "identity.write" in refused.json()["error"]["message"]

    async with store.begin(TenantScope(org_id=ORG)) as uow:
        found = await uow.identity.find_user_by_email("grace@acme.test")
    assert found is None, "a refused request must not have a side effect"


async def test_the_refusal_does_not_say_whether_the_email_already_exists(
    deployment: tuple[AsyncClient, FakePersistence, str],
) -> None:
    """The same denial, whether or not the target address is already taken.

    A caller who may not create an account must not be able to use this
    route to probe for one. The permission check runs before the email is
    ever looked up, so the message is identical either way.
    """
    client, store, secret = deployment
    await client.post(
        PRINCIPALS,
        json={"email": "grace@acme.test", "display_name": "Grace", "password": "correct-horse"},
        headers=bearer(secret),
    )

    tokens = TokenService(gateway=store)
    viewer = await issue_token(
        store, tokens, user_id="vic", role=Role.VIEWER, node_id=TEAM_PAYMENTS
    )
    refused_existing = await client.post(
        PRINCIPALS,
        json={
            "email": "grace@acme.test",
            "display_name": "Someone else",
            "password": "another-one",
        },
        headers=bearer(viewer),
    )
    refused_new = await client.post(
        PRINCIPALS,
        json={
            "email": "nobody-yet@acme.test",
            "display_name": "Nobody yet",
            "password": "another-one",
        },
        headers=bearer(viewer),
    )

    assert refused_existing.status_code == 403
    assert refused_new.status_code == 403
    existing_message = refused_existing.json()["error"]["message"]
    new_message = refused_new.json()["error"]["message"]
    assert existing_message == new_message
    assert "grace@acme.test" not in existing_message
    assert "already" not in existing_message.lower()
    assert "exists" not in existing_message.lower()


async def test_a_duplicate_email_is_refused_with_a_conflict(
    deployment: tuple[AsyncClient, FakePersistence, str],
) -> None:
    client, _, secret = deployment
    body = {"email": "grace@acme.test", "display_name": "Grace", "password": "correct-horse"}
    first = await client.post(PRINCIPALS, json=body, headers=bearer(secret))
    assert first.status_code == 201

    second = await client.post(
        PRINCIPALS,
        json={**body, "display_name": "A different Grace", "password": "another-passphrase"},
        headers=bearer(secret),
    )
    assert second.status_code == 409

    listed = (await client.get(PRINCIPALS, headers=bearer(secret))).json()["users"]
    matching = [entry for entry in listed if entry["email"] == "grace@acme.test"]
    assert len(matching) == 1


async def test_the_creation_leaves_an_audit_row_naming_the_actor_and_the_principal(
    deployment: tuple[AsyncClient, FakePersistence, str],
) -> None:
    client, store, secret = deployment
    created = (
        await client.post(
            PRINCIPALS,
            json={"email": "grace@acme.test", "display_name": "Grace", "password": "correct-horse"},
            headers=bearer(secret),
        )
    ).json()

    async with store.begin(TenantScope(org_id=ORG)) as uow:
        events = await uow.audit.query()
    matching = [event for event in events if event.action == "principal.create"]
    assert len(matching) == 1
    event = matching[0]
    assert event.actor_id == "ada"
    assert event.resource_id == created["user_id"]
    assert event.detail["email"] == "grace@acme.test"
    assert event.detail["display_name"] == "Grace"
    # "ada" signed in with an org-wide owner grant (no team), so the node the
    # audit row names is the organisation as a whole — the same spelling
    # `add_grant` already uses for a grant with no `node_id`.
    assert event.detail["node_id"] == "organisation"


async def test_a_team_scoped_admin_may_create_and_the_audit_row_names_that_team(
    deployment: tuple[AsyncClient, FakePersistence, str],
) -> None:
    """The same asymmetric guard `/identity/grants` already has, not a new one.

    An admin holding ``identity.write`` only at ``payments`` may still create
    a person — the permission is resolved at the caller's own node exactly as
    it is for granting a role — and the audit row says which node that was,
    rather than defaulting to the organisation.
    """
    client, store, _ = deployment
    tokens = TokenService(gateway=store)
    admin = await issue_token(store, tokens, user_id="pat", role=Role.ADMIN, node_id=TEAM_PAYMENTS)

    created = (
        await client.post(
            PRINCIPALS,
            json={"email": "grace@acme.test", "display_name": "Grace", "password": "correct-horse"},
            headers=bearer(admin),
        )
    ).json()
    assert created["email"] == "grace@acme.test"

    async with store.begin(TenantScope(org_id=ORG)) as uow:
        events = await uow.audit.query()
    event = next(event for event in events if event.action == "principal.create")
    assert event.actor_id == "pat"
    assert event.detail["node_id"] == TEAM_PAYMENTS
