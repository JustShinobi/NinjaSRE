"""Onboarding an estate over HTTP: ask the vendor, look, then commit.

Three routes, and each of them exists because of something that goes wrong
without it.

**The deep verify** is separate from the credential verify beside it, and the
separation is what these assertions are mostly about: the cheap one answers from
what this deployment stored, and the expensive one makes live vendor calls. A
deployment that composed no way to reach a vendor answers 404 with a sentence
rather than an empty document, because an empty document reads as a clean bill.

**The preview** stores nothing. The assertion that matters is the one taken
*after* it runs: the estate is still empty. An operator who does not recognise
the counts has nothing to undo.

**Registering the source** writes the recurring job the scheduler claims. The
assertion is against the schedule store rather than against the response, so a
route that answered convincingly and wrote nothing fails.

Everything goes through ``create_app``, the composed route table and a real
issued token, so "which permission does this actually demand" is answered by the
guard rather than by a comment.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from config.constants.estate import ESTATE_DISCOVERY_JOB_KIND
from gateway.http.app import create_app
from gateway.http.state import GatewayState
from integrations._base.discovery import declare
from platform.estate.discovery.port import (
    DiscoveredResource,
    DiscoveryMode,
    DiscoveryPage,
    SweepBudget,
)
from platform.estate.kinds import KIND_CONTAINER, KIND_NODE
from platform.identity.permissions import Role
from platform.persistence.ports import EstateQuery, TenantScope
from tests.unit.gateway.http.conftest import ORG, TEAM_PAYMENTS, Deployment, issue_token

pytestmark = pytest.mark.unit

INTEGRATION = "proxmox"
SCOPE = TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)

ZONES = {"10.20.10.0/24": "mgmt", "10.20.20.0/24": "infra", "10.20.30.0/24": "apps"}

#: A report shaped like the one ``ProxmoxVerifier`` produces. Shaped rather than
#: produced, because what is under test here is the route: whether the vendor's
#: own answer reaches a caller unflattened.
PRIVILEGE_REPORT: dict[str, Any] = {
    "cluster": "HAL9000",
    "node_count": 2,
    "privileges": {
        "read_sufficient": False,
        "missing_read": ["Sys.Syslog on / — without it, nothing can read the cluster log"],
        "granted_at": "Datacenter → Permissions",
    },
}


@dataclass(slots=True)
class StubSource:
    """A discovery source that answers one page and counts how often it was asked."""

    resources: tuple[DiscoveredResource, ...] = ()
    complete: bool = True
    calls: list[DiscoveryMode] = field(default_factory=list)

    @property
    def declaration(self) -> Any:
        return declare(
            INTEGRATION,
            kinds=(KIND_NODE, KIND_CONTAINER),
            interval_seconds=300,
            rate_limit_per_minute=120,
            max_provider_calls=150,
        )

    async def discover(
        self,
        *,
        mode: DiscoveryMode,
        cursor: str = "",
        budget: SweepBudget,
    ) -> DiscoveryPage:
        del cursor, budget
        self.calls.append(mode)
        return DiscoveryPage(resources=self.resources, complete=self.complete, provider_calls=7)


def _guest(vmid: int, *, address: str, status: str = "running") -> DiscoveredResource:
    return DiscoveredResource(
        kind=KIND_CONTAINER,
        native_id=f"lxc/{vmid}",
        display_name=f"ct{vmid}",
        parent_native_id="node/pve01",
        provider_status=status,
        attributes={"address": address},
        signals={"address": address},
    )


CLUSTER = (
    DiscoveredResource(
        kind=KIND_NODE,
        native_id="node/pve01",
        display_name="pve01",
        provider_status="online",
        attributes={"address": "10.20.10.11"},
        signals={"address": "10.20.10.11"},
    ),
    _guest(100, address="10.20.20.4"),
    _guest(101, address="10.20.30.7"),
    _guest(102, address="10.20.30.8", status="stopped"),
    _guest(103, address="192.168.68.9"),
)


@pytest.fixture
def source() -> StubSource:
    return StubSource(resources=CLUSTER)


@pytest.fixture
async def wired(deployment: Deployment, source: StubSource) -> AsyncIterator[AsyncClient]:
    """A client over a deployment that has a source and a deep verifier composed."""

    async def deep_verify(name: str, team_id: str) -> Mapping[str, Any] | None:
        del team_id
        return PRIVILEGE_REPORT if name == INTEGRATION else None

    state: GatewayState = deployment.state
    state.deep_verifier = deep_verify
    state.discovery_sources = {INTEGRATION: source}

    transport = ASGITransport(app=create_app(state))
    async with AsyncClient(transport=transport, base_url="http://gateway.test") as http:
        yield http


@pytest.fixture
async def manager_token(deployment: Deployment) -> str:
    """A token holding ``estate.manage`` and ``integration.manage``."""
    return await issue_token(
        deployment.gateway,
        deployment.tokens,
        user_id="ada",
        role=Role.OPERATOR,
        node_id=TEAM_PAYMENTS,
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


def _headers(secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}"}


# --- the deep verify ----------------------------------------------------------


async def test_a_deep_verify_returns_the_vendors_own_report(
    wired: AsyncClient, manager_token: str
) -> None:
    response = await wired.post(
        f"/v1/integrations/{INTEGRATION}/verify/report", headers=_headers(manager_token)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["integration"] == INTEGRATION
    assert body["report"]["privileges"]["read_sufficient"] is False
    assert body["report"]["privileges"]["missing_read"] == [
        "Sys.Syslog on / — without it, nothing can read the cluster log"
    ]


async def test_an_integration_with_no_deep_verifier_is_refused_with_a_sentence(
    wired: AsyncClient, manager_token: str
) -> None:
    response = await wired.post(
        "/v1/integrations/datadog/verify/report", headers=_headers(manager_token)
    )

    assert response.status_code == 404
    detail = response.json()["error"]["message"]
    assert "datadog" in detail
    assert "/v1/integrations/datadog/verify" in detail


async def test_a_deployment_that_composed_no_deep_verifier_says_so(
    deployment: Deployment, manager_token: str
) -> None:
    """Not an empty report. An empty report reads as a clean bill of health."""
    transport = ASGITransport(app=create_app(deployment.state))
    async with AsyncClient(transport=transport, base_url="http://gateway.test") as http:
        response = await http.post(
            f"/v1/integrations/{INTEGRATION}/verify/report", headers=_headers(manager_token)
        )

    assert response.status_code == 404
    assert "no deep verifier is composed" in response.json()["error"]["message"]


async def test_a_viewer_cannot_make_this_deployment_call_somebody_elses_cluster(
    wired: AsyncClient, viewer_token: str
) -> None:
    response = await wired.post(
        f"/v1/integrations/{INTEGRATION}/verify/report", headers=_headers(viewer_token)
    )

    assert response.status_code == 403


# --- the preview --------------------------------------------------------------


async def test_the_preview_counts_what_a_sweep_would_find(
    wired: AsyncClient, manager_token: str
) -> None:
    response = await wired.post(
        "/v1/estate/discovery/preview",
        headers=_headers(manager_token),
        json={"integration": INTEGRATION, "zones": ZONES},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["nodes"] == 1
    assert body["guests"] == 4
    assert body["running"] == 4
    assert body["by_zone"] == {"apps": 2, "infra": 1, "mgmt": 1}
    assert body["zones"] == 3
    assert body["unplaced"] == 1
    assert body["complete"] is True
    assert body["provider_calls"] == 7


async def test_the_preview_stores_nothing(
    wired: AsyncClient, manager_token: str, deployment: Deployment
) -> None:
    """The assertion is taken after the call, against the estate itself."""
    await wired.post(
        "/v1/estate/discovery/preview",
        headers=_headers(manager_token),
        json={"integration": INTEGRATION, "zones": ZONES},
    )

    async with deployment.gateway.begin(SCOPE) as uow:
        found = await uow.estate.query(EstateQuery(limit=100, include_absent=True))
        sweeps = await uow.estate.last_sweep(INTEGRATION)
    assert found == ()
    assert sweeps is None


async def test_a_preview_with_no_zone_map_reports_everything_unplaced(
    wired: AsyncClient, manager_token: str
) -> None:
    """Honest rather than empty: nothing is placed, and it says how many."""
    response = await wired.post(
        "/v1/estate/discovery/preview",
        headers=_headers(manager_token),
        json={"integration": INTEGRATION},
    )

    body = response.json()
    assert body["by_zone"] == {}
    assert body["unplaced"] == 5


async def test_previewing_an_integration_nothing_is_pointed_at_names_the_next_step(
    wired: AsyncClient, manager_token: str
) -> None:
    response = await wired.post(
        "/v1/estate/discovery/preview",
        headers=_headers(manager_token),
        json={"integration": "vsphere"},
    )

    assert response.status_code == 404
    detail = response.json()["error"]["message"]
    assert "vsphere" in detail
    assert "credential" in detail


# --- committing to it ---------------------------------------------------------


async def test_confirming_registers_the_sweep_the_scheduler_claims(
    wired: AsyncClient, manager_token: str, deployment: Deployment
) -> None:
    response = await wired.post(
        "/v1/estate/discovery/sources",
        headers=_headers(manager_token),
        json={"integration": INTEGRATION},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == f"{ESTATE_DISCOVERY_JOB_KIND}:{INTEGRATION}"
    assert body["interval_seconds"] == 300

    async with deployment.gateway.begin(SCOPE) as uow:
        stored = await uow.schedules.get_job(body["job_id"])
    assert stored is not None
    assert stored.kind == ESTATE_DISCOVERY_JOB_KIND
    assert stored.enabled is True
    assert stored.payload["source"] == INTEGRATION
    assert stored.next_run_at is not None


async def test_confirming_twice_leaves_one_sweep_rather_than_two(
    wired: AsyncClient, manager_token: str, deployment: Deployment
) -> None:
    """The job identifier is derived from the source, so a second confirmation
    updates the schedule instead of sweeping the cluster twice as often."""
    for _ in range(2):
        await wired.post(
            "/v1/estate/discovery/sources",
            headers=_headers(manager_token),
            json={"integration": INTEGRATION},
        )

    async with deployment.gateway.begin(SCOPE) as uow:
        jobs = await uow.schedules.list_jobs(kind=ESTATE_DISCOVERY_JOB_KIND, limit=50)
    assert len(jobs) == 1


async def test_a_viewer_cannot_point_this_deployment_at_a_cluster(
    wired: AsyncClient, viewer_token: str
) -> None:
    response = await wired.post(
        "/v1/estate/discovery/sources",
        headers=_headers(viewer_token),
        json={"integration": INTEGRATION},
    )

    assert response.status_code == 403
