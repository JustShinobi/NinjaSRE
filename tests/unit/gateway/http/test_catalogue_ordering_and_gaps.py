"""The catalogue, ordered by what the estate found, and honest about what is absent.

Two things this response has to do that a list of ninety names does not.

**Put the ones this deployment plainly runs at the top, with the address filled
in.** Discovery has already been through the cluster; it knows one of the
containers is called ``prometheus`` and where it is. An operator scrolling an
alphabet to find that out again is an operator doing work the deployment did.

**Say what it does not cover, and why.** Gatus and NetBox are absences somebody
weighed and decided against. Served with the catalogue rather than from a route
nobody knows to ask, because the question they answer is exactly the one the
catalogue is being read to answer, and an absence discovered by not finding it
is discovered at the worst moment.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.http.app import create_app
from platform.estate.kinds import KIND_CONTAINER
from platform.identity.permissions import Role
from platform.persistence.ports import TenantScope
from platform.persistence.ports.estate_repository import Resource
from tests.unit.gateway.http.conftest import ORG, TEAM_PAYMENTS, Deployment, issue_token

pytestmark = pytest.mark.unit

SCOPE = TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)
SEEN = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)


def _container(name: str, address: str) -> Resource:
    return Resource(
        resource_id=f"proxmox:lxc:{name}",
        kind=KIND_CONTAINER,
        source="proxmox",
        native_id=f"lxc/HAL9000/{name}",
        display_name=name,
        attributes={"address": address, "vmid": 100},
        last_seen_at=SEEN,
    )


@pytest.fixture
async def manager_token(deployment: Deployment) -> str:
    """The catalogue demands ``integration.manage``: it is the screen a
    credential is written from, not a listing a viewer browses."""
    return await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="ada",
        role=Role.OPERATOR,
        node_id=TEAM_PAYMENTS,
    )


@pytest.fixture
async def discovered(deployment: Deployment) -> AsyncIterator[AsyncClient]:
    """A deployment whose estate holds the observability stack by name."""
    async with deployment.gateway.begin(SCOPE) as uow:
        await uow.estate.upsert(_container("prometheus", "10.20.20.37"))
        await uow.estate.upsert(_container("grafana", "10.20.20.33"))
        await uow.estate.upsert(_container("adguard", "10.20.20.4"))

    transport = ASGITransport(app=create_app(deployment.state))
    async with AsyncClient(transport=transport, base_url="http://gateway.test") as http:
        yield http


@pytest.fixture
async def undiscovered(deployment: Deployment) -> AsyncIterator[AsyncClient]:
    """A deployment that has not swept anything yet."""
    transport = ASGITransport(app=create_app(deployment.state))
    async with AsyncClient(transport=transport, base_url="http://gateway.test") as http:
        yield http


async def _catalogue(http: AsyncClient, token: str) -> dict[str, Any]:
    response = await http.get("/v1/integrations", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


# --- what the estate makes obvious ----------------------------------------------


async def test_a_vendor_the_estate_holds_comes_first_with_its_address(
    discovered: AsyncClient, manager_token: str
) -> None:
    body = await _catalogue(discovered, manager_token)
    names = [entry["name"] for entry in body["integrations"]]

    assert names[:2] == ["grafana", "prometheus"], names[:5]
    first = {entry["name"]: entry for entry in body["integrations"][:2]}
    assert first["prometheus"]["suggested"]["address"] == "http://10.20.20.37:9090"
    assert first["grafana"]["suggested"]["address"] == "http://10.20.20.33:3000"


async def test_a_suggestion_says_which_resource_it_was_derived_from(
    discovered: AsyncClient, manager_token: str
) -> None:
    """Derived, not typed — and traceable, or an operator re-checks it anyway."""
    body = await _catalogue(discovered, manager_token)
    prometheus = next(entry for entry in body["integrations"] if entry["name"] == "prometheus")

    assert prometheus["suggested"]["from_resource"] == "proxmox:lxc:prometheus"
    assert "10.20.20.37" in prometheus["suggested"]["because"]


async def test_everything_the_estate_says_nothing_about_carries_no_suggestion(
    discovered: AsyncClient, manager_token: str
) -> None:
    body = await _catalogue(discovered, manager_token)

    datadog = next(entry for entry in body["integrations"] if entry["name"] == "datadog")
    assert datadog["suggested"] is None


async def test_a_deployment_that_has_swept_nothing_keeps_the_alphabet(
    undiscovered: AsyncClient, manager_token: str
) -> None:
    body = await _catalogue(undiscovered, manager_token)
    names = [entry["name"] for entry in body["integrations"]]

    assert names == sorted(names)
    assert all(entry["suggested"] is None for entry in body["integrations"])


# --- what it does not cover ------------------------------------------------------


async def test_gatus_and_netbox_are_recorded_gaps_with_their_reasons(
    undiscovered: AsyncClient, manager_token: str
) -> None:
    """Acceptance 5."""
    body = await _catalogue(undiscovered, manager_token)
    gaps = {gap["integration"]: gap for gap in body["known_gaps"]}

    for name in ("gatus", "netbox"):
        assert name in gaps, f"{name} is absent from the catalogue and from its gap list"
        assert gaps[name]["cause"] == "not_built"
        assert gaps[name]["reason"].strip()
        assert gaps[name]["resolution"].strip()


async def test_a_decision_is_told_apart_from_an_impossibility(
    undiscovered: AsyncClient, manager_token: str
) -> None:
    """ "We weighed this" and "the architecture forbids it" are different answers
    to "can you add it", and an operator asking deserves the right one."""
    body = await _catalogue(undiscovered, manager_token)
    causes = {gap["integration"]: gap["cause"] for gap in body["known_gaps"]}

    assert causes["gatus"] == "not_built"
    assert causes["postgresql"] == "unreachable"


async def test_no_recorded_gap_is_also_an_installed_integration(
    undiscovered: AsyncClient, manager_token: str
) -> None:
    body = await _catalogue(undiscovered, manager_token)
    installed = {entry["name"] for entry in body["integrations"]}

    assert installed.isdisjoint({gap["integration"] for gap in body["known_gaps"]})
