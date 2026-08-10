"""A resource's page says which source answers each question about it.

The block exists because of one number. Asked "how much memory is this container
using", an agent inside the container answers from cgroup accounting seen
through a namespace that was never built to publish it — and the answer is
wrong, plausible, and indistinguishable from the right one. The estate knows
this resource is a container and knows its identifier on the host; the map is
where those two facts turn into "ask Prometheus, filtered by vmid".

The second half is the absences. A deployment with no log store gets a named
gap, because a blank on the page reads as "there are no logs" and sends somebody
looking for a fault in the container.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from config.constants.signals import (
    SIGNAL_KEY_VMID,
    SIGNAL_QUESTION_LOGS,
    SIGNAL_QUESTION_PRESSURE,
    SIGNAL_QUESTION_UP,
    SIGNAL_QUESTIONS,
)
from gateway.http.app import create_app
from platform.credentials.handles import CredentialHandle
from platform.credentials.schemas import CredentialSchemaRegistry
from platform.credentials.vault import Vault
from platform.estate.kinds import KIND_CONTAINER
from platform.identity.permissions import Role
from platform.persistence.ports import TenantScope
from platform.persistence.ports.estate_repository import Resource
from tests.unit.gateway.http.conftest import ORG, TEAM_PAYMENTS, Deployment, issue_token

pytestmark = pytest.mark.unit

SCOPE = TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)
RESOURCE_ID = "proxmox:lxc:HAL9000:100"

#: The credential each integration's schema will accept. Not secrets; the point
#: is only that a handle exists, which is what "configured" means here.
CREDENTIALS: dict[str, dict[str, str]] = {
    "proxmox": {"api_token": "ninjasre@pve!estate=00000000-0000-0000-0000-000000000000"},
    "prometheus": {"token": "ninjasre-scenario-token-000000"},
    "loki": {"token": "ninjasre-scenario-token-000000"},
}


def _adguard() -> Resource:
    """The container from the cluster's own memcg-OOM postmortem."""
    return Resource(
        resource_id=RESOURCE_ID,
        kind=KIND_CONTAINER,
        source="proxmox",
        native_id="lxc/HAL9000/2025-01-01T00:00:00/100",
        display_name="adguard",
        correlation_key="HAL9000/lxc/100",
        attributes={"vmid": 100, "address": "10.20.20.4", "memory_bytes": 536_870_912},
        last_seen_at=datetime(2026, 8, 10, 12, 0, tzinfo=UTC),
    )


async def _seed(deployment: Deployment, *, integrations: tuple[str, ...]) -> None:
    """Put the container in the estate and the named credentials in the vault."""
    async with deployment.gateway.begin(SCOPE) as uow:
        await uow.estate.upsert(_adguard())

    from integrations._catalogue.discovery import catalogue

    schemas = CredentialSchemaRegistry.from_schemas(
        *(entry.descriptor.schema for entry in catalogue())
    )
    vault = Vault(gateway=deployment.gateway, schemas=schemas)
    for name in integrations:
        await vault.store(
            SCOPE, CredentialHandle(integration=name, team_id=TEAM_PAYMENTS), CREDENTIALS[name]
        )


@pytest.fixture
async def viewer_token(deployment: Deployment) -> str:
    return await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="viv",
        role=Role.VIEWER,
        node_id=TEAM_PAYMENTS,
    )


@pytest.fixture
async def watched(deployment: Deployment) -> AsyncIterator[AsyncClient]:
    """A deployment with the hypervisor, a metric store and a log store."""
    await _seed(deployment, integrations=("proxmox", "prometheus", "loki"))
    transport = ASGITransport(app=create_app(deployment.state))
    async with AsyncClient(transport=transport, base_url="http://gateway.test") as http:
        yield http


@pytest.fixture
async def unwatched(deployment: Deployment) -> AsyncIterator[AsyncClient]:
    """A deployment that discovered an estate and connected nothing to watch it."""
    await _seed(deployment, integrations=("proxmox",))
    transport = ASGITransport(app=create_app(deployment.state))
    async with AsyncClient(transport=transport, base_url="http://gateway.test") as http:
        yield http


def _headers(secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}"}


async def _signals(http: AsyncClient, token: str) -> dict[str, object]:
    response = await http.get(f"/v1/estate/resources/{RESOURCE_ID}", headers=_headers(token))
    assert response.status_code == 200, response.text
    return response.json()["signals"]


async def test_a_containers_pressure_resolves_to_the_host_series_keyed_by_vmid(
    watched: AsyncClient, viewer_token: str
) -> None:
    """Acceptance 2, at the surface an investigation reads it from."""
    signals = await _signals(watched, viewer_token)

    pressure = next(
        entry
        for entry in signals["sources"]  # type: ignore[index]
        if entry["question"] == SIGNAL_QUESTION_PRESSURE
    )
    assert pressure["integration"] == "prometheus"
    assert pressure["keyed_by"] == SIGNAL_KEY_VMID
    assert pressure["key"] == "100"
    assert "kernel" in pressure["detail"]


async def test_up_and_logs_both_resolve_for_a_watched_resource(
    watched: AsyncClient, viewer_token: str
) -> None:
    """Acceptance 3's positive half."""
    signals = await _signals(watched, viewer_token)
    answered = {
        entry["question"]: entry["integration"]
        for entry in signals["sources"]  # type: ignore[index]
    }

    assert answered[SIGNAL_QUESTION_UP] == "proxmox"
    assert answered[SIGNAL_QUESTION_LOGS] == "loki"


async def test_every_question_appears_exactly_once_across_the_two_lists(
    watched: AsyncClient, viewer_token: str
) -> None:
    signals = await _signals(watched, viewer_token)

    answered = [entry["question"] for entry in signals["sources"]]  # type: ignore[index]
    named = [entry["question"] for entry in signals["missing"]]  # type: ignore[index]
    assert sorted(answered + named) == sorted(SIGNAL_QUESTIONS)


async def test_a_question_nothing_answers_names_what_would(
    unwatched: AsyncClient, viewer_token: str
) -> None:
    """Acceptance 3's other half: a gap with a reason, not a blank."""
    signals = await _signals(unwatched, viewer_token)

    logs = next(
        entry
        for entry in signals["missing"]  # type: ignore[index]
        if entry["question"] == SIGNAL_QUESTION_LOGS
    )
    assert logs["wanted"] == ["loki", "openobserve"]
    assert logs["why"].strip()


async def test_the_block_carries_no_credential(watched: AsyncClient, viewer_token: str) -> None:
    signals = await _signals(watched, viewer_token)

    printed = repr(signals)
    for secret in ("token", "secret", "password"):
        assert secret not in printed.lower(), f"a signal map rendered a {secret}"
