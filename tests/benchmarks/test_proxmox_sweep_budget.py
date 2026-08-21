"""NFR-001: a two-node cluster with fifty guests, inside its declared budget.

The number this defends is a call count, not a latency. A discovery sweep runs
against somebody's own hardware — the reference cluster's primary node sits at
63% CPU before anything asks it a question — and a sweep that costs four hundred
calls every five minutes is a sweep an operator turns off, at which point the
estate stops being maintained and nobody is told.

So the budget is declared in ``integrations/proxmox/discovery.py`` as
``MAX_SWEEP_CALLS`` and this measures the real thing against it: fifty guests
across two nodes, the whole sweep, every call counted. The arithmetic that has to
hold is two cluster-wide calls, six cluster-detail calls, four per node, and one
per guest — which is where "prefer the cluster-wide resource list and reserve
per-guest reads for investigation" stops being a design note and becomes a
number.

The time budget is measured too, against the sweep's own ceiling rather than
against a figure invented here: this runs over a scripted transport with no
network in it, so what it proves is that the *assembly* is not the expensive
part. What a real cluster costs is dominated by the hop this file does not have.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import pytest

from integrations._base.retry import RetryPolicy
from integrations._base.transport import RequestContext
from integrations.proxmox.client import ProxmoxClient
from integrations.proxmox.discovery import MAX_SWEEP_CALLS, ProxmoxDiscovery
from integrations.proxmox.schema import API_BASE
from platform.credentials.proxy.model import OutboundResponse, ProxyRequest
from platform.estate.discovery.port import DiscoveryMode, SweepBudget
from tests.support.proxmox import PRIMARY, SECONDARY, ClusterState, recorded

pytestmark = pytest.mark.benchmark

CONTEXT = RequestContext(org_id="acme", team_id="homelab", capability="proxmox_sweep")
NO_RETRY = RetryPolicy(max_attempts=1)

#: The shape NFR-001 names: two nodes, fifty guests.
GUEST_COUNT = 50

#: What one sweep of that shape may cost. Two cluster-wide calls, six cluster
#: detail calls, four per node, and one per guest.
EXPECTED_CALLS = 2 + 6 + (4 * 2) + GUEST_COUNT

#: Wall-clock ceiling for assembling the page, with no network in the way. Two
#: orders of magnitude below the sweep's own bound, because everything this
#: measures is dictionary work — if it ever approaches the sweep budget, the
#: assembly has become the expensive part and that is the defect.
ASSEMBLY_BUDGET_SECONDS = 1.0


@dataclass(slots=True)
class ScriptedCluster:
    """A recorded two-node cluster grown to fifty guests, behind the transport."""

    responses: dict[str, Any]
    calls: list[str] = field(default_factory=list)

    async def forward(self, request: ProxyRequest) -> OutboundResponse:
        """Answer ``request`` from the script, counting the call."""
        path = urlsplit(request.url).path.removeprefix(API_BASE)
        self.calls.append(path)
        payload = self.responses.get(path, [])
        return OutboundResponse(
            200,
            {"content-type": "application/json"},
            json.dumps({"data": payload}).encode("utf-8"),
        )


def fifty_guests() -> ScriptedCluster:
    """Return the reference cluster with fifty guests spread across its two nodes."""
    cluster = recorded(ClusterState.HEALTHY)
    responses = dict(cluster.responses)

    resources = [row for row in responses["/cluster/resources"] if row.get("type") != "lxc"]
    resources = [row for row in resources if row.get("type") != "qemu"]
    for index in range(GUEST_COUNT):
        vmid = 200 + index
        node = PRIMARY if index % 2 else SECONDARY
        resources.append(
            {
                "id": f"lxc/{vmid}",
                "type": "lxc",
                "vmid": vmid,
                "name": f"guest-{vmid}",
                "node": node,
                "status": "running",
                "maxcpu": 2,
                "maxmem": 2_147_483_648,
                "maxdisk": 34_359_738_368,
                "uptime": 604_800,
            }
        )
        responses[f"/nodes/{node}/lxc/{vmid}/config"] = {
            "hostname": f"guest-{vmid}",
            "cores": 2,
            "memory": 2048,
            "ostype": "debian",
            "meta": f"creation-lxc=9.2.6,ctime={1_700_000_000 + index}",
        }
    responses["/cluster/resources"] = resources
    return ScriptedCluster(responses=responses)


async def test_a_two_node_cluster_with_fifty_guests_sweeps_inside_its_call_budget() -> None:
    transport = fifty_guests()
    client = ProxmoxClient(transport=transport, context=CONTEXT, retry=NO_RETRY)
    source = ProxmoxDiscovery(client=client)

    page = await source.discover(mode=DiscoveryMode.FULL, budget=SweepBudget())

    assert page.complete, "the sweep suspended, so this measured less than the whole cluster"
    assert page.provider_calls == len(transport.calls)
    assert page.provider_calls == EXPECTED_CALLS, (
        f"the sweep cost {page.provider_calls} calls where the shape predicts "
        f"{EXPECTED_CALLS}. A change that adds a per-guest read multiplies by fifty."
    )
    assert page.provider_calls <= MAX_SWEEP_CALLS
    assert page.provider_calls <= source.declaration.max_provider_calls


async def test_the_page_is_assembled_in_a_time_the_network_would_dominate() -> None:
    transport = fifty_guests()
    client = ProxmoxClient(transport=transport, context=CONTEXT, retry=NO_RETRY)
    source = ProxmoxDiscovery(client=client)

    started = time.perf_counter()
    page = await source.discover(mode=DiscoveryMode.FULL, budget=SweepBudget())
    elapsed = time.perf_counter() - started

    assert len(page.resources) >= GUEST_COUNT
    assert elapsed < ASSEMBLY_BUDGET_SECONDS, (
        f"assembling {len(page.resources)} resources took {elapsed:.3f}s, which is the "
        f"assembly becoming the expensive part rather than the cluster round trip"
    )
