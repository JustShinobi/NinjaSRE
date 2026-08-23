"""The public address the console reads for every incident, and the gateway resolves.

`GET /v1/incidents` and `GET /v1/incidents/{id}` are what the console's list
and detail pages read. This feature adds a public address distinct from the
internal key: short, URL-safe, and what a listing or a detail response now
carries so nothing built on top of them has to derive one on its own or fall
back to the composite, reserved-character-carrying primary key.

The three claims below: the public address rides on both response shapes,
in a form nothing needs to escape; the detail route resolves either
spelling — the public address and the internal key — to the same incident;
and an address nothing carries comes back as a named absence, never a
server error.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.http.app import create_app
from gateway.http.state import GatewayState
from platform.identity.permissions import Role
from platform.identity.tokens import TokenService
from platform.incidents.lifecycle import IncidentLifecycle, IncidentRaise
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.config_repository import ConfigNode, ConfigNodeKind
from platform.persistence.ports.incident_store import (
    IncidentOrigin,
    IncidentSubject,
    is_public_incident_id,
)
from platform.persistence.ports.transaction import TenantScope
from tests.unit.gateway.http.conftest import (
    ORG,
    TEAM_PAYMENTS,
    FakeInvestigationRunner,
    issue_token,
)

RESERVED = frozenset(":@+/?#[]%")


@dataclass(slots=True)
class Deployment:
    client: AsyncClient
    gateway: FakePersistence
    secret: str


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
    secret = await issue_token(
        gateway, tokens, user_id="ada", role=Role.OWNER, node_id=TEAM_PAYMENTS
    )
    state = GatewayState(gateway=gateway, tokens=tokens, investigator=FakeInvestigationRunner())
    app = create_app(state)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://gateway.test") as client:
        yield Deployment(client=client, gateway=gateway, secret=secret)


async def _raised_incident(deployment: Deployment, correlation_key: str) -> str:
    """Raise one incident through the lifecycle and return its internal key."""
    now = datetime.now(UTC)
    async with deployment.gateway.begin(TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        incident = await lifecycle.raise_incident(
            IncidentRaise(
                correlation_key=correlation_key,
                title="cedar is down",
                summary="the blackbox probe against cedar has failed",
                origin=IncidentOrigin.ALERT,
                origin_id="InstanceDown",
                severity="critical",
                subjects=(
                    IncidentSubject(resource_id="cedar", detail="unhealthy", observed_at=now),
                ),
                team_node_id=TEAM_PAYMENTS,
                cause="InstanceDown fired for cedar",
            ),
            now=now,
        )
    return incident.incident_id


async def _get(deployment: Deployment, path: str) -> Any:
    return await deployment.client.get(
        path, headers={"Authorization": f"Bearer {deployment.secret}"}
    )


# --- Claim: listing and detail both carry an escape-free public address -----------


async def test_the_listing_carries_a_public_address_needing_no_escape(
    deployment: Deployment,
) -> None:
    await _raised_incident(deployment, "alert:InstanceDown:cedar")

    response = await _get(deployment, "/v1/incidents")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["incidents"], "the fixture raised one incident; the listing must carry it"
    row = body["incidents"][0]
    assert "public_id" in row, f"no public_id on a listing row; keys are {sorted(row)}"
    public_id = row["public_id"]
    assert public_id != "", "every incident must carry a public address"
    found = RESERVED & set(public_id)
    assert not found, f"{public_id!r} carries reserved character(s) {sorted(found)}"


async def test_the_detail_carries_the_same_public_address_the_listing_does(
    deployment: Deployment,
) -> None:
    internal_id = await _raised_incident(deployment, "alert:InstanceDown:cedar")

    listing = (await _get(deployment, "/v1/incidents")).json()
    detail = (await _get(deployment, f"/v1/incidents/{internal_id}")).json()

    assert detail["incident"]["public_id"] == listing["incidents"][0]["public_id"]


# --- Claim: the detail route resolves either spelling to the same incident --------


async def test_the_detail_route_resolves_the_public_address_and_the_internal_key_alike(
    deployment: Deployment,
) -> None:
    internal_id = await _raised_incident(deployment, "alert:InstanceDown:cedar")

    by_internal_key = (await _get(deployment, f"/v1/incidents/{internal_id}")).json()
    public_id = by_internal_key["incident"]["public_id"]
    assert is_public_incident_id(public_id), (
        f"{public_id!r} does not match the public address grammar"
    )

    by_public_address = await _get(deployment, f"/v1/incidents/{public_id}")
    assert by_public_address.status_code == 200, by_public_address.text
    assert by_public_address.json()["incident"]["incident_id"] == internal_id


async def test_an_unknown_public_address_is_a_named_absence_not_a_server_error(
    deployment: Deployment,
) -> None:
    await _raised_incident(deployment, "alert:InstanceDown:cedar")

    response = await _get(deployment, "/v1/incidents/inc_0000000000000000")

    assert response.status_code == 404, response.text
    assert "no incident" in response.json()["error"]["message"].lower()


__all__: list[str] = []
