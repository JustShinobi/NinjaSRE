"""Machine tokens over HTTP: issued, listed, revoked — and no longer accumulated.

Issuing a second token for a purpose that already has a live one used to leave
both live, forever: the console's list of "bootstrap — investigation.read,
token.manage" rows was the visible symptom of exactly this. A new issuance for
the same owner and the same purpose now supersedes the one it replaces instead.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from platform.identity.audit.recorder import AuditContext
from platform.identity.permissions import Role
from platform.persistence.ports.audit_repository import ActorKind
from platform.persistence.ports.transaction import TenantScope
from tests.unit.gateway.http.conftest import ORG, Deployment, issue_token

pytestmark = pytest.mark.anyio

TOKENS = "/identity/tokens"


async def _owner(deployment: Deployment) -> dict[str, str]:
    secret = await issue_token(
        deployment.gateway, deployment.tokens, user_id="ada", role=Role.OWNER, node_id=None
    )
    return {"authorization": f"Bearer {secret}"}


async def test_issuing_for_a_purpose_that_already_has_a_live_token_supersedes_it(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _owner(deployment)

    first = await client.post(TOKENS, headers=headers, json={"name": "ci-runner"})
    assert first.status_code == 201
    first_id = first.json()["token"]["token_id"]

    second = await client.post(TOKENS, headers=headers, json={"name": "ci-runner"})
    assert second.status_code == 201

    # The defect this reproduces: a second issuance for the same purpose left
    # both tokens live and said nothing about it.
    assert second.json()["superseded"] == [first_id]

    listed = (await client.get(TOKENS, headers=headers)).json()["tokens"]
    superseded_row = next(token for token in listed if token["token_id"] == first_id)
    assert superseded_row["revoked"] is True


async def test_the_supersession_is_recorded_in_the_audit_trail(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _owner(deployment)
    first = await client.post(TOKENS, headers=headers, json={"name": "ci-runner"})
    first_id = first.json()["token"]["token_id"]

    await client.post(TOKENS, headers=headers, json={"name": "ci-runner"})

    async with deployment.gateway.begin(TenantScope(org_id=ORG)) as uow:
        events = await uow.audit.query(resource_id=first_id)

    assert any("superseded" in str(event.detail) for event in events)


async def test_a_different_purpose_for_the_same_owner_does_not_supersede_anything(
    client: AsyncClient, deployment: Deployment
) -> None:
    headers = await _owner(deployment)
    first = await client.post(TOKENS, headers=headers, json={"name": "ci-runner"})
    first_id = first.json()["token"]["token_id"]

    second = await client.post(TOKENS, headers=headers, json={"name": "backup-job"})
    assert second.json()["superseded"] == []

    listed = (await client.get(TOKENS, headers=headers)).json()["tokens"]
    assert next(token for token in listed if token["token_id"] == first_id)["revoked"] is False


async def test_a_second_browser_sign_in_does_not_revoke_the_first(deployment: Deployment) -> None:
    """Two tabs, two devices: a session is not a purpose the console supersedes.

    Only the console's own issuance route asks `TokenService.issue` to
    supersede — a signed-in session is minted through
    `platform/identity/local_accounts.py`, which never sets that flag, so two
    concurrent sign-ins both keep working. Exercised directly against
    `TokenService`, which is what both that module and the route call.
    """
    scope = TenantScope(org_id=ORG)
    context = AuditContext(actor_kind=ActorKind.USER, actor_id="ada")
    await issue_token(
        deployment.gateway, deployment.tokens, user_id="ada", role=Role.OWNER, node_id=None
    )

    first = await deployment.tokens.issue(scope, context, user_id="ada", name="Console sign-in")
    second = await deployment.tokens.issue(scope, context, user_id="ada", name="Console sign-in")

    assert second.superseded == ()
    async with deployment.gateway.begin(scope) as uow:
        tokens = await uow.identity.tokens_for_user("ada")
    assert next(token for token in tokens if token.token_id == first.token.token_id).is_revoked is (
        False
    )
