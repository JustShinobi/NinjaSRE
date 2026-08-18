"""The credential an operator pastes into Alertmanager, and what it may do.

Receiving an alert is not permission to investigate anything. The token this
feature asks an operator to issue is a machine token scoped to one permission,
and the assertions here are as much about what it *cannot* do as about what it
can — a delivery credential that could read the run history would be a secret
sitting in somebody else's configuration file with the whole deployment behind
it.

The bearer path is additive: a source configured with a signature or a shared
secret verifies exactly as it did, and the token is only consulted when nothing
else did.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.http.app import create_app
from gateway.http.state import GatewayState
from platform.identity.audit.recorder import AuditContext
from platform.identity.permissions import Permission, Role, permissions_for
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.audit_repository import ActorKind
from platform.persistence.ports.config_repository import ConfigNode, ConfigNodeKind
from platform.persistence.ports.identity_repository import RoleBinding, User
from platform.persistence.ports.incident_store import IncidentQuery
from platform.persistence.ports.transaction import TenantScope
from tests.unit.gateway.http.conftest import ORG, TEAM_PAYMENTS, FakeInvestigationRunner

pytestmark = pytest.mark.asyncio


def firing() -> dict[str, Any]:
    return {
        "receiver": "ninjasre",
        "status": "firing",
        "groupKey": '{}:{alertname="ContainerMemoryHigh"}::1',
        "commonLabels": {"alertname": "ContainerMemoryHigh", "severity": "critical"},
        "alerts": [
            {
                "status": "firing",
                "labels": {"alertname": "ContainerMemoryHigh", "vmid": "110"},
                "annotations": {"summary": "memory usage above 90%"},
                "startsAt": "2026-08-10T12:00:00Z",
                "endsAt": "0001-01-01T00:00:00Z",
            }
        ],
    }


@dataclass(slots=True)
class Deployment:
    client: AsyncClient
    state: GatewayState
    gateway: FakePersistence
    tokens: TokenService
    runner: FakeInvestigationRunner


@pytest.fixture
async def deployment() -> AsyncIterator[Deployment]:
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    async with gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.config.upsert(
            ConfigNode(
                node_id=TEAM_PAYMENTS, kind=ConfigNodeKind.TEAM, name=TEAM_PAYMENTS, parent_id=ORG
            )
        )
    tokens = TokenService(gateway=gateway)
    runner = FakeInvestigationRunner()
    state = GatewayState(gateway=gateway, tokens=tokens, investigator=runner)
    # No webhook route is configured at all: this is the deployment an operator
    # has just installed, where the only way in is the token the panel issues.
    app = create_app(state)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://gateway.test") as client:
        yield Deployment(client=client, state=state, gateway=gateway, tokens=tokens, runner=runner)


async def machine_token(
    deployment: Deployment,
    *,
    user_id: str,
    permissions: tuple[Permission, ...],
    unscoped: bool = False,
) -> str:
    """Return the secret of a token issued to ``user_id``, holding ``permissions``.

    ``unscoped`` stands the credential in for the person who holds it rather
    than for one declared purpose, the way a session or a personal token
    does — it keeps resolving to whatever role bindings ``user_id`` carries
    at the moment the token is used, not to ``permissions`` alone. Every
    delivery credential in this module leaves it at the default, because the
    whole point under test is that a scope it was never issued stays out of
    reach.
    """
    scope = TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)
    async with deployment.gateway.begin(scope) as uow:
        await uow.identity.upsert_user(
            User(user_id=user_id, email=f"{user_id}@acme.test", display_name=user_id)
        )
        await uow.identity.upsert_role_binding(
            RoleBinding(
                binding_id=f"grant-{user_id}",
                user_id=user_id,
                role=Role.RESPONDER.value,
                node_id=TEAM_PAYMENTS,
            )
        )
    issued = await deployment.tokens.issue(
        scope,
        AuditContext(actor_kind=ActorKind.USER, actor_id=user_id),
        user_id=user_id,
        name=f"{user_id}-token",
        node_id=TEAM_PAYMENTS,
        permissions=permissions,
        unscoped=unscoped,
    )
    return issued.secret


async def deliver(deployment: Deployment, secret: str) -> Any:
    body = json.dumps(firing()).encode("utf-8")
    return await deployment.client.post(
        "/webhooks/alertmanager",
        content=body,
        headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/json"},
    )


# --- The permission itself --------------------------------------------------------


def test_delivering_an_alert_is_its_own_permission() -> None:
    """Named, so it can be granted alone. Receiving is not investigating."""
    assert Permission.WEBHOOK_DELIVER.value == "webhook.deliver"


def test_it_is_treated_as_a_write_because_it_opens_an_incident() -> None:
    """A delivery raises an incident and starts a run; nothing about that observes."""
    assert not Permission.WEBHOOK_DELIVER.is_read_only


def test_no_read_role_holds_it() -> None:
    """A viewer's credential leaking must not become an ingestion endpoint."""
    assert Permission.WEBHOOK_DELIVER not in permissions_for(Role.VIEWER)
    assert Permission.WEBHOOK_DELIVER in permissions_for(Role.RESPONDER)


# --- What a token holding only it can, and cannot, do -----------------------------


async def test_a_token_scoped_to_it_delivers_an_alert(deployment: Deployment) -> None:
    """The whole of what an operator pastes into Alertmanager."""
    secret = await machine_token(
        deployment, user_id="alertmanager", permissions=(Permission.WEBHOOK_DELIVER,)
    )

    response = await deliver(deployment, secret)

    assert response.status_code == 202, response.text
    assert response.json()["run_id"]


async def test_the_delivery_lands_on_the_team_the_token_was_issued_for(
    deployment: Deployment,
) -> None:
    """Routing and authentication stay one decision — now made by the token."""
    secret = await machine_token(
        deployment, user_id="alertmanager", permissions=(Permission.WEBHOOK_DELIVER,)
    )
    await deliver(deployment, secret)

    async with deployment.gateway.begin(TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)) as uow:
        incidents = await uow.incidents.query(IncidentQuery(limit=10))

    assert len(incidents) == 1
    assert incidents[0].team_node_id == TEAM_PAYMENTS


async def test_the_same_token_cannot_read_the_run_history(deployment: Deployment) -> None:
    """The point of the permission: a secret in somebody else's file reads nothing."""
    secret = await machine_token(
        deployment, user_id="alertmanager", permissions=(Permission.WEBHOOK_DELIVER,)
    )

    response = await deployment.client.get(
        "/v1/runs", headers={"Authorization": f"Bearer {secret}"}
    )

    assert response.status_code == 403, response.text


async def test_a_token_without_it_cannot_deliver(deployment: Deployment) -> None:
    """A read credential is not an ingestion endpoint."""
    secret = await machine_token(
        deployment, user_id="reader", permissions=(Permission.INVESTIGATION_READ,)
    )

    response = await deliver(deployment, secret)

    assert response.status_code == 401, response.text
    assert deployment.runner.started == []


async def test_a_secret_that_is_not_a_token_at_all_is_refused(deployment: Deployment) -> None:
    """Unchanged: nothing verified, so nothing is ingested."""
    response = await deliver(deployment, "not-a-token")

    assert response.status_code == 401, response.text
    assert deployment.runner.started == []


# --- The route that issues it -----------------------------------------------------


async def test_the_permission_is_grantable_through_the_token_route(
    deployment: Deployment,
) -> None:
    """T-006's own sentence: issued by ``POST /identity/tokens``, and no wider."""
    # The credential calling the route stands in for the administrator, not
    # for one declared purpose — a session-shaped, unscoped token, the way an
    # operator's own sign-in would authenticate here. `Role.ADMIN` (granted
    # below, after issuance) is what actually carries `token.manage`; an
    # empty `permissions` on a scoped token would hold nothing at all.
    admin = await machine_token(deployment, user_id="operator", permissions=(), unscoped=True)
    async with deployment.gateway.begin(TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)) as uow:
        await uow.identity.upsert_role_binding(
            RoleBinding(
                binding_id="grant-operator-admin",
                user_id="operator",
                role=Role.ADMIN.value,
                node_id=TEAM_PAYMENTS,
            )
        )

    created = await deployment.client.post(
        "/identity/tokens",
        headers={"Authorization": f"Bearer {admin}"},
        json={
            "name": "alertmanager",
            "node_id": TEAM_PAYMENTS,
            "permissions": [Permission.WEBHOOK_DELIVER.value],
        },
    )
    assert created.status_code == 201, created.text
    issued = created.json()
    assert issued["token"]["scopes"] == [Permission.WEBHOOK_DELIVER.value]

    delivered = await deliver(deployment, issued["secret"])
    assert delivered.status_code == 202, delivered.text
