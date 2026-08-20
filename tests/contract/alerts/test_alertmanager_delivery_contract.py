"""The Alertmanager delivery contract: the grouped body Alertmanager really
sends, the delivery token that authenticates it, and what one delivery from
this source is allowed to do to the incident it opens.

``tests/contract/alerts/fixtures_alertmanager_delivery.py`` holds the payloads
this file consumes: a genuine grouped ``firing`` notification with two
members, a byte-for-byte-equal retry of it, and the ``resolved`` notification
the same group sends once every member clears. No committed test read that
module before this one.

Five claims: the real body is accepted; a delivery with no token is refused;
a delivery with a revoked token is refused the same way; the retry is
recognised as the delivery already processed and the incident count does not
move; the resolution is a distinct delivery from the firing, and it is the one
that records the incident's closing.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.http.app import create_app
from gateway.http.state import GatewayState
from platform.identity.audit.recorder import AuditContext
from platform.identity.permissions import Permission, Role
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.audit_repository import ActorKind
from platform.persistence.ports.config_repository import ConfigNode, ConfigNodeKind
from platform.persistence.ports.identity_repository import RoleBinding, User
from platform.persistence.ports.incident_store import IncidentQuery, IncidentState
from platform.persistence.ports.transaction import TenantScope
from tests.contract.alerts.fixtures_alertmanager_delivery import (
    ALERTMANAGER_FIRING_GROUPED,
    ALERTMANAGER_FIRING_GROUPED_RETRY,
    ALERTMANAGER_RESOLVED_SAME_GROUP,
)
from tests.unit.gateway.http.conftest import ORG, TEAM_PAYMENTS, FakeInvestigationRunner

pytestmark = pytest.mark.asyncio


@dataclass(slots=True)
class Deployment:
    client: AsyncClient
    gateway: FakePersistence
    tokens: TokenService
    runner: FakeInvestigationRunner


@pytest.fixture
async def deployment() -> AsyncIterator[Deployment]:
    """A deployment with no shared-secret Alertmanager route configured.

    A delivery token is the only way in — exactly what an operator has after
    following Alert intake: nothing wired ahead of time that would stand in
    for the shared-secret receivers this feature does not touch.
    """
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
    app = create_app(state)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://gateway.test") as client:
        yield Deployment(client=client, gateway=gateway, tokens=tokens, runner=runner)


async def _delivery_token(
    deployment: Deployment, *, user_id: str = "alertmanager"
) -> tuple[str, str]:
    """Issue a token scoped to exactly the delivery permission.

    Returns ``(token_id, secret)`` — the credential Alert intake issues and an
    operator pastes into the Alertmanager receiver, scoped through a real role
    binding rather than a permission list nothing granted (``permissions`` is
    a ceiling on what the owning user already holds, never a grant on its own).
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
        name=f"{user_id}-delivery-token",
        node_id=TEAM_PAYMENTS,
        permissions=(Permission.WEBHOOK_DELIVER,),
    )
    return issued.token.token_id, issued.secret


async def _deliver(deployment: Deployment, payload: Mapping[str, Any], *, token: str | None) -> Any:
    """POST ``payload`` to the real Alertmanager intake path, unmodified."""
    body = json.dumps(dict(payload)).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return await deployment.client.post("/webhooks/alertmanager", content=body, headers=headers)


async def _incident_count(deployment: Deployment) -> int:
    """Return how many incidents exist on the team the token delivers to."""
    async with deployment.gateway.begin(TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)) as uow:
        incidents = await uow.incidents.query(IncidentQuery(limit=50))
    return len(incidents)


# --- The real grouped body is accepted --------------------------------------------


async def test_the_real_grouped_body_is_accepted(deployment: Deployment) -> None:
    """The exact v4 grouped shape — groupKey, commonLabels, an alerts array
    with two members — is accepted without this repository asking for a
    format of its own, and opens a real incident with a real investigation."""
    _, secret = await _delivery_token(deployment)

    response = await _deliver(deployment, ALERTMANAGER_FIRING_GROUPED, token=secret)

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["incident_id"]
    assert body["run_id"]


# --- Authentication: no token, and a revoked one, are both refused ----------------


async def test_no_token_is_refused_with_401(deployment: Deployment) -> None:
    """Nothing verifies an unauthenticated delivery, and it opens nothing."""
    response = await _deliver(deployment, ALERTMANAGER_FIRING_GROUPED, token=None)

    assert response.status_code == 401, response.text
    assert deployment.runner.started == []
    assert await _incident_count(deployment) == 0


async def test_a_revoked_token_is_refused_with_401(deployment: Deployment) -> None:
    """Revoking after issuance produces the same 401 an absent token does — not
    a 500, and not a silent acceptance of a credential that used to work. A
    different test from the missing-token one above: this one is the only
    proof in this file that revocation itself, not merely absence, is
    honoured on the delivery path.
    """
    token_id, secret = await _delivery_token(deployment)
    scope = TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)
    was_live = await deployment.tokens.revoke(
        scope, AuditContext(actor_kind=ActorKind.USER, actor_id="operator"), token_id
    )
    assert was_live  # precondition: the token really was live before this revoked it

    response = await _deliver(deployment, ALERTMANAGER_FIRING_GROUPED, token=secret)

    assert response.status_code == 401, response.text
    assert deployment.runner.started == []
    assert await _incident_count(deployment) == 0


# --- Deduplication: an identical redelivery does not raise a second incident -----


async def test_an_identical_redelivery_does_not_open_a_second_incident(
    deployment: Deployment,
) -> None:
    """Being recognised as a duplicate is a claim about the response; not
    opening a second incident is a claim about the store — checked here
    directly on the incident count rather than trusted from the response's
    own word.
    """
    _, secret = await _delivery_token(deployment)

    first = await _deliver(deployment, ALERTMANAGER_FIRING_GROUPED, token=secret)
    assert first.status_code == 202, first.text
    count_after_first = await _incident_count(deployment)
    assert count_after_first == 1

    second = await _deliver(deployment, ALERTMANAGER_FIRING_GROUPED_RETRY, token=secret)

    assert second.status_code == 202, second.text
    assert second.json().get("duplicate_delivery") is True
    assert await _incident_count(deployment) == count_after_first


# --- Resolution: a distinct delivery that closes what the firing opened ----------


async def test_a_resolution_is_a_distinct_delivery_that_closes_the_incident(
    deployment: Deployment,
) -> None:
    """The resolution's status and each alert's instants differ from the
    firing's, so its derived delivery identity differs too — it must not be
    answered as the same delivery. And it must record the closing on the
    incident itself, not merely say a word in its own response body.
    """
    _, secret = await _delivery_token(deployment)

    opened = await _deliver(deployment, ALERTMANAGER_FIRING_GROUPED, token=secret)
    assert opened.status_code == 202, opened.text
    incident_id = opened.json()["incident_id"]

    resolution = await _deliver(deployment, ALERTMANAGER_RESOLVED_SAME_GROUP, token=secret)

    assert resolution.status_code == 202, resolution.text
    assert resolution.json().get("duplicate_delivery") is None

    async with deployment.gateway.begin(TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)) as uow:
        incident = await uow.incidents.get(incident_id)

    assert incident is not None
    assert incident.state == IncidentState.RESOLVED
    assert incident.closed_at is not None
    assert incident.self_resolved is True


__all__: list[str] = []
