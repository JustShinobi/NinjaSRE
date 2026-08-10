"""What the signal map is worth, measured by removing it and asking again.

The scenario is this cluster's own history. A container running AdGuard was
killed repeatedly by the memory cgroup while every reading anybody looked at
said the machine had memory to spare — because the readings anybody looked at
came from *inside* the container, where an LXC guest sees the host's
`/proc/meminfo` rather than its own cgroup limit. The number was well-formed,
plausible, and about the wrong machine.

So this measures the mechanism rather than describing it. One recorded
Prometheus, holding both series honestly: the host-side series for guest 100
says it is at 94% of the 512 MiB ceiling it will be killed at, and the in-guest
series says 31%, because 31% is the *host's* utilisation and that is exactly
what an LXC guest reads there.

Two arms over that one recording.

**With the map**, the capability asks the estate which source answers *pressure*
for a container, is told Prometheus keyed by vmid, and reads 0.94.

**Without it**, the query is the one an investigation writes when nothing told
it otherwise — the in-guest series, by name — and reads 0.31.

The arms differ because the mechanism was removed, not because the fixture said
so: both arms run the real capability against the same recorded vendor, and the
vendor answers whatever series it is asked for.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from core.capability.result import CapabilityResult
from integrations._base.access import IntegrationAccess, bind, current, restore
from integrations._base.transport import InProcessProxyTransport
from integrations._catalogue.discovery import catalogue
from integrations.prometheus import PROFILE as PROMETHEUS_PROFILE  # noqa: F401
from integrations.prometheus.client import PrometheusClient
from integrations.prometheus.pressure import (
    GUEST_MEMORY_TOTAL,
    GUEST_MEMORY_USED,
    NODE_MEMORY_AVAILABLE,
    NODE_MEMORY_TOTAL,
)
from integrations.prometheus.tools import prometheus_resource_pressure
from platform.credentials.handles import CredentialHandle
from platform.credentials.proxy.app import create_proxy_app
from platform.credentials.proxy.audit import ResolutionAuditor
from platform.credentials.proxy.engine import ProxyEngine
from platform.credentials.proxy.injection import InjectionRuleRegistry
from platform.credentials.proxy.model import OutboundRequest, OutboundResponse
from platform.credentials.proxy.resolution import CredentialResolver
from platform.credentials.schemas import CredentialSchemaRegistry
from platform.credentials.vault import Vault
from platform.estate.kinds import KIND_CONTAINER
from platform.persistence.fakes import FakePersistence
from tests.synthetic.integration_scenarios import AT, ORG_ID, SCOPE, TEAM_ID

pytestmark = pytest.mark.synthetic

INTEGRATION = "prometheus"

#: The guest from the cluster's own postmortem.
VMID = 100

#: What the guest is actually at, against the ceiling it is killed at. Above any
#: threshold an operator would set, which is the point: the correct reading is
#: alarming and the incorrect one is not.
GUEST_MEMORY_RATIO = 0.94

#: What an in-guest collector reports, which is the *host's* utilisation. Below
#: every threshold, which is why the container was killed four times before
#: anybody looked anywhere else.
HOST_MEMORY_RATIO = 0.31

#: The query an investigation writes when nothing tells it where to look. Not a
#: strawman: it is the standard node-exporter expression, and it is what runs
#: inside a container that shares the host's kernel.
NAIVE_QUERY = f"1 - ({NODE_MEMORY_AVAILABLE} / {NODE_MEMORY_TOTAL})"

#: Above this a memory-pressure conclusion is drawn. Named here rather than
#: inlined so the two arms are compared against one number.
ALARMING_RATIO = 0.90


@dataclass(slots=True)
class RecordedPrometheus:
    """One Prometheus, answering honestly about whichever series it is asked for.

    The whole scenario turns on this being *one* recording. A fixture that
    answered differently per arm would prove that the fixture differs; this
    answers per series, so the arms differ because they asked different
    questions.
    """

    asked: list[str] = field(default_factory=list)

    async def send(self, request: OutboundRequest, *, timeout_seconds: float) -> OutboundResponse:
        query = _query_of(request)
        self.asked.append(query)
        return _json({"data": {"result": _series_for(query)}})


def _query_of(request: OutboundRequest) -> str:
    """Return the PromQL expression ``request`` carried."""
    from urllib.parse import parse_qs, urlparse

    return parse_qs(urlparse(str(request.url)).query).get("query", [""])[0]


def _series_for(query: str) -> list[dict[str, Any]]:
    """Return what a Prometheus holding both readings would answer."""
    if GUEST_MEMORY_USED in query and f'id="lxc/{VMID}"' in query:
        return [{"metric": {"id": f"lxc/{VMID}"}, "values": [[1, str(GUEST_MEMORY_RATIO)]]}]
    if NODE_MEMORY_AVAILABLE in query:
        # What the guest sees, and it is the host's figure. This line is the
        # whole incident.
        return [{"metric": {"instance": "pve01:9100"}, "values": [[1, str(HOST_MEMORY_RATIO)]]}]
    return [{"metric": {"id": f"lxc/{VMID}"}, "values": [[1, "0.10"]]}]


def _json(payload: object) -> OutboundResponse:
    return OutboundResponse(
        200, {"content-type": "application/json"}, json.dumps(payload).encode("utf-8")
    )


async def _against(recorded: RecordedPrometheus, call: Any) -> Any:
    """Run ``call`` against ``recorded``, through the real credential proxy."""
    descriptor = next(entry.descriptor for entry in catalogue() if entry.name == INTEGRATION)
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG_ID, "Acme")

    schemas = CredentialSchemaRegistry.from_schemas(descriptor.schema)
    await Vault(gateway=gateway, schemas=schemas).store(
        SCOPE,
        CredentialHandle(integration=INTEGRATION, team_id=TEAM_ID),
        {"token": "ninjasre-scenario-token-000000"},
    )
    engine = ProxyEngine(
        resolver=CredentialResolver(gateway=gateway, schemas=schemas),
        rules=InjectionRuleRegistry.from_rules(descriptor.rule),
        sender=recorded,
        auditor=ResolutionAuditor(gateway=gateway),
        clock=lambda: AT,
    )
    previous = bind(
        IntegrationAccess(
            transport=InProcessProxyTransport(create_proxy_app(engine)),
            org_id=ORG_ID,
            team_id=TEAM_ID,
        )
    )
    try:
        return await call()
    finally:
        restore(previous)


def _reading(result: CapabilityResult, name: str) -> float:
    """Return the ratio one named reading came back with."""
    readings = result.value["readings"]
    for reading in readings:
        if reading["name"] == name:
            return float(reading["samples"][0]["values"][0][1])
    raise AssertionError(f"no {name} reading in {readings}")


async def _naive_reading() -> float:
    """Return what the same Prometheus answers a query written without the map.

    The same client, the same proxy, the same recording. Only the expression is
    different, and it is the one an investigation writes when nothing has told it
    that a container's counters are the host's.
    """
    recorded = RecordedPrometheus()

    async def read() -> float:
        access = current()
        assert access is not None
        client = access.client(PrometheusClient, capability="ablation_arm")
        found = await client.query_metric(NAIVE_QUERY, start="1", end="2", limit=5)
        assert found.items, "the ablation arm read nothing, so there is nothing to compare"
        return float(found.items[0]["values"][0][1])

    reading: float = await _against(recorded, read)
    return reading


# --- with the map ---------------------------------------------------------------


async def test_with_the_map_the_investigation_reads_the_host_side_series() -> None:
    recorded = RecordedPrometheus()

    result = await _against(
        recorded,
        lambda: prometheus_resource_pressure(
            resource_kind=KIND_CONTAINER, vmid=VMID, start="1", end="2"
        ),
    )

    assert result.ok, result.error
    assert _reading(result, "memory") == pytest.approx(GUEST_MEMORY_RATIO)
    assert _reading(result, "memory") > ALARMING_RATIO


async def test_the_query_it_sent_names_the_host_series_and_this_guest() -> None:
    recorded = RecordedPrometheus()

    await _against(
        recorded,
        lambda: prometheus_resource_pressure(
            resource_kind=KIND_CONTAINER, vmid=VMID, start="1", end="2"
        ),
    )

    memory = next(query for query in recorded.asked if GUEST_MEMORY_USED in query)
    assert GUEST_MEMORY_TOTAL in memory
    assert f'id="lxc/{VMID}"' in memory
    assert NODE_MEMORY_AVAILABLE not in " ".join(recorded.asked)


async def test_the_result_carries_why_that_source_was_the_right_one() -> None:
    """A conclusion nobody can check is a conclusion nobody should act on."""
    recorded = RecordedPrometheus()

    result = await _against(
        recorded,
        lambda: prometheus_resource_pressure(
            resource_kind=KIND_CONTAINER, vmid=VMID, start="1", end="2"
        ),
    )

    assert "kernel" in str(result.value["why_this_source"])
    assert str(VMID) in result.evidence[0].summary


# --- with the map switched off ---------------------------------------------------


async def test_without_the_map_the_same_prometheus_reports_the_hosts_number() -> None:
    """The ablation arm. The vendor is the same recording; the question is not."""
    reading = await _naive_reading()

    assert reading == pytest.approx(HOST_MEMORY_RATIO)
    assert reading < ALARMING_RATIO


async def test_the_ablation_arm_asks_a_question_about_the_wrong_machine() -> None:
    recorded = RecordedPrometheus()

    async def read() -> None:
        access = current()
        assert access is not None
        client = access.client(PrometheusClient, capability="ablation_arm")
        await client.query_metric(NAIVE_QUERY, start="1", end="2", limit=5)

    await _against(recorded, read)

    assert any(NODE_MEMORY_AVAILABLE in query for query in recorded.asked)
    assert not any(f'id="lxc/{VMID}"' in query for query in recorded.asked)


# --- the delta ------------------------------------------------------------------


async def test_the_two_arms_reach_opposite_conclusions_from_one_recording() -> None:
    """The number this scenario publishes.

    One scenario, two arms. With the signal map the memory reading is above the
    threshold a conclusion is drawn at; without it, from the same Prometheus, it
    is below — so the mechanism's contribution here is one scenario from wrong to
    right, which is the whole delta this suite reports and is not zero.
    """
    with_map = await _against(
        RecordedPrometheus(),
        lambda: prometheus_resource_pressure(
            resource_kind=KIND_CONTAINER, vmid=VMID, start="1", end="2"
        ),
    )
    without_map = await _naive_reading()

    correct_with_map = _reading(with_map, "memory") > ALARMING_RATIO
    correct_without_map = without_map > ALARMING_RATIO

    assert (correct_with_map, correct_without_map) == (True, False), (
        "the signal map's contribution to this scenario is supposed to be the "
        "difference between diagnosing a memory-cgroup kill and concluding the "
        "container had memory to spare"
    )
