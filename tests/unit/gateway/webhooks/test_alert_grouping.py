"""One problem, many notifications, one investigation.

Alertmanager already groups. The failure this pins is the platform undoing that
by opening an investigation per notification — and this cluster has two
postmortems that would each have produced a wall of them: AdGuard recurring OOM,
and a ClickHouse log storm. Their payload shapes are the fixtures below.

The other half is the converse, and it is the one resolution bought: two
containers complaining under the same rule carry the same alert name and the
same components, so a key that stopped at the alert would link the second to the
first's investigation and leave nobody looking at it.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from core.domain.alerts.normalisation import NormalisedAlert, RawAlert, adapter_for
from core.domain.alerts.sources import AlertSource
from gateway.http.app import create_app
from gateway.http.services import InvestigationStart
from gateway.http.state import GatewayState
from gateway.webhooks.router import WebhookSourceConfig
from gateway.webhooks.verification.shared_secret import SharedSecretVerifier
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.config_repository import ConfigNode, ConfigNodeKind
from platform.persistence.ports.estate_repository import Resource
from platform.persistence.ports.incident_store import IncidentQuery, IncidentState
from platform.persistence.ports.transaction import TenantScope
from tests.unit.gateway.http.conftest import ORG, TEAM_PAYMENTS, FakeInvestigationRunner

pytestmark = pytest.mark.asyncio

SECRET = "alertmanager-delivery-secret"

#: The two guests the cluster's own postmortems are about. Both are containers,
#: both are in the apps zone, and both would fire the same rule.
ADGUARD_VMID = 110
CLICKHOUSE_VMID = 111


def container(vmid: int, name: str, address: str) -> Resource:
    return Resource(
        resource_id=f"proxmox:container/hal9000/{vmid}",
        kind="container",
        source="proxmox",
        native_id=f"container/hal9000/{vmid}",
        display_name=name,
        team_node_id=TEAM_PAYMENTS,
        attributes={"vmid": vmid, "address": address, "zone": "apps"},
    )


def group(
    *,
    vmid: int,
    alert_name: str,
    delivery: str,
    status: str = "firing",
    summary: str = "",
) -> dict[str, Any]:
    """Return one Alertmanager notification of one group.

    The group key is in Alertmanager's own shape — the labels the receiver
    groups by — with a delivery discriminator appended. ``delivery`` varies
    where a real Alertmanager would repeat a notification of an unchanged
    group: this deployment reads ``groupKey`` as the delivery identifier, so a
    re-notification has to differ there to be seen at all rather than answered
    as a duplicate.
    """
    return {
        "receiver": "ninjasre",
        "status": status,
        "groupKey": f'{{}}:{{alertname="{alert_name}", vmid="{vmid}"}}::{delivery}',
        "commonLabels": {"alertname": alert_name, "severity": "critical"},
        "alerts": [
            {
                "status": status,
                "labels": {"alertname": alert_name, "severity": "critical", "vmid": str(vmid)},
                "annotations": {"summary": summary or f"{alert_name} on guest {vmid}"},
                "startsAt": "2026-08-10T12:00:00Z",
                "endsAt": "0001-01-01T00:00:00Z" if status == "firing" else "2026-08-10T12:40:00Z",
            }
        ],
    }


def adguard_oom(delivery: str, status: str = "firing") -> dict[str, Any]:
    """The recurring out-of-memory shape: one guest, one rule, many notifications."""
    return group(
        vmid=ADGUARD_VMID,
        alert_name="ContainerMemoryHigh",
        delivery=delivery,
        status=status,
        summary="memory usage above 90% for ten minutes",
    )


def clickhouse_storm(delivery: str) -> dict[str, Any]:
    """The log-storm shape: the same rule, a different guest."""
    return group(
        vmid=CLICKHOUSE_VMID,
        alert_name="ContainerMemoryHigh",
        delivery=delivery,
        summary="memory usage above 90% for ten minutes",
    )


@dataclass(slots=True)
class Ingress:
    client: AsyncClient
    state: GatewayState
    gateway: FakePersistence
    runner: FakeInvestigationRunner

    @property
    def scope(self) -> TenantScope:
        return TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)


@pytest.fixture
async def ingress() -> AsyncIterator[Ingress]:
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    async with gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.config.upsert(
            ConfigNode(
                node_id=TEAM_PAYMENTS, kind=ConfigNodeKind.TEAM, name=TEAM_PAYMENTS, parent_id=ORG
            )
        )
    async with gateway.begin(TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)) as uow:
        await uow.estate.upsert(container(ADGUARD_VMID, "adguard", "10.20.20.10"))
        await uow.estate.upsert(container(CLICKHOUSE_VMID, "clickhouse", "10.20.20.11"))

    runner = FakeInvestigationRunner()
    state = GatewayState(gateway=gateway, tokens=TokenService(gateway=gateway), investigator=runner)
    app = create_app(
        state,
        webhook_routes={
            "alertmanager": (
                WebhookSourceConfig(
                    verifier=SharedSecretVerifier(secret=SECRET, header="Authorization"),
                    org_id=ORG,
                    team_node_id=TEAM_PAYMENTS,
                ),
            )
        },
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://gateway.test") as client:
        yield Ingress(client=client, state=state, gateway=gateway, runner=runner)


async def deliver(ingress: Ingress, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    response = await ingress.client.post(
        "/webhooks/alertmanager",
        content=body,
        headers={"Authorization": f"Bearer {SECRET}", "Content-Type": "application/json"},
    )
    assert response.status_code == 202, response.text
    if ingress.state.background_runs:
        await asyncio.gather(*tuple(ingress.state.background_runs))
    return dict(response.json())


# --- The adapter ------------------------------------------------------------------


def test_the_adapter_carries_the_group_the_upstream_put_the_alert_in() -> None:
    """Whose group this is, kept rather than parsed back out of an identifier later."""
    alert = adapter_for(AlertSource.ALERTMANAGER).normalise(RawAlert(payload=adguard_oom("first")))

    assert alert.group_key == '{}:{alertname="ContainerMemoryHigh", vmid="110"}::first'


def test_the_group_survives_the_record_an_alert_is_stored_as() -> None:
    """A run read back tomorrow says which group raised it, or it is not evidence."""
    alert = adapter_for(AlertSource.ALERTMANAGER).normalise(RawAlert(payload=adguard_oom("first")))

    assert NormalisedAlert.from_record(alert.to_record()) == alert


def test_a_source_that_does_not_group_carries_no_group() -> None:
    """Empty rather than invented: not every sender has the concept."""
    alert = adapter_for(AlertSource.WEBHOOK).normalise(
        RawAlert(payload={"alert_name": "CustomAlert", "summary": "something broke"})
    )

    assert alert.group_key == ""


# --- A storm of one group ---------------------------------------------------------


async def test_a_storm_of_notifications_of_one_group_is_one_investigation(
    ingress: Ingress,
) -> None:
    """The AdGuard shape: eight notifications of one recurring condition."""
    responses = [await deliver(ingress, adguard_oom(f"n{index}")) for index in range(8)]

    assert len(ingress.runner.started) == 1
    assert responses[0]["linked"] is False
    assert all(response["linked"] is True for response in responses[1:])
    assert {response["run_id"] for response in responses} == {responses[0]["run_id"]}


async def test_every_delivery_of_the_storm_lands_on_the_one_incident(
    ingress: Ingress,
) -> None:
    """Linked, not discarded: an operator who thinks it is two can still split it."""
    await deliver(ingress, adguard_oom("n0"))
    await deliver(ingress, adguard_oom("n1"))

    async with ingress.gateway.begin(ingress.scope) as uow:
        incidents = await uow.incidents.query(IncidentQuery(limit=10))

    assert len(incidents) == 1
    assert incidents[0].subject_ids == (f"proxmox:container/hal9000/{ADGUARD_VMID}",)
    # Which group the upstream said this was, kept where somebody asking "why is
    # this one incident" can read it.
    assert incidents[0].subjects[0].evidence["group"].startswith("{}:{alertname=")


async def test_the_same_rule_on_a_second_guest_is_a_second_investigation(
    ingress: Ingress,
) -> None:
    """Same alert name, same components, different machine — and two problems."""
    first = await deliver(ingress, adguard_oom("n0"))
    second = await deliver(ingress, clickhouse_storm("n0"))

    assert second["linked"] is False
    assert second["run_id"] != first["run_id"]
    assert len(ingress.runner.started) == 2


# --- Firing, then resolved --------------------------------------------------------


async def test_a_firing_then_a_resolution_of_one_group_is_one_investigation(
    ingress: Ingress,
) -> None:
    """Acceptance 3, against the Alertmanager payload shape rather than in the abstract."""
    started = await deliver(ingress, adguard_oom("n0"))
    ended = await deliver(ingress, adguard_oom("n1", status="resolved"))

    assert ended["resolution"] == "linked"
    assert ended["run_id"] == started["run_id"]
    assert len(ingress.runner.started) == 1


async def test_the_resolution_closes_the_incident_the_firing_opened(
    ingress: Ingress,
) -> None:
    """An upstream that went green and a deployment still showing it open disagree."""
    await deliver(ingress, adguard_oom("n0"))
    await deliver(ingress, adguard_oom("n1", status="resolved"))

    async with ingress.gateway.begin(ingress.scope) as uow:
        incidents = await uow.incidents.query(IncidentQuery(limit=10))

    assert len(incidents) == 1
    assert incidents[0].state is IncidentState.RESOLVED
    assert incidents[0].self_resolved is True


# --- One failure, several rules, one investigation ---------------------------
#
# The grouping above is Alertmanager's: it groups notifications of *one rule*.
# What it cannot group is several rules firing about one thing, because each
# rule is its own group with its own fingerprint. So one container being shut
# down produced five incidents here and five investigations, none of which knew
# the other four existed, and four of which reached the same wrong answer
# independently.
#
# The relation is the subject, which alert resolution recorded before any of
# this ran — and the fifth alert in that measured burst arrived inside the same
# minute and was about a different container, so arrival is exactly the signal
# that would have got it wrong.


@dataclass(slots=True)
class _BlockingRunner(FakeInvestigationRunner):
    """A runner whose investigation is still going when the next alert lands.

    The shared fake finishes the moment it is awaited, which makes every run
    complete before the second delivery — the one state in which there is
    correctly nothing to join. A real investigation takes the best part of a
    minute and the second symptom arrives inside it.
    """

    release: asyncio.Event = field(default_factory=asyncio.Event)

    async def investigate(self, request: InvestigationStart) -> str:
        self.started.append(request)
        await self.release.wait()
        return "done"


async def _deliver_without_waiting(ingress: Ingress, payload: dict[str, Any]) -> dict[str, Any]:
    """Post an alert and leave whatever it started still running."""
    response = await ingress.client.post(
        "/webhooks/alertmanager",
        content=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {SECRET}", "Content-Type": "application/json"},
    )
    assert response.status_code == 202, response.text
    # One pass of the loop, so the task the route created reaches its first
    # await and the run is recorded as running before the next alert arrives.
    await asyncio.sleep(0)
    return dict(response.json())


@pytest.fixture
async def busy(ingress: Ingress) -> AsyncIterator[Ingress]:
    """The same ingress, with a runner that does not finish on its own."""
    runner = _BlockingRunner()
    ingress.state.investigator = runner
    ingress.runner = runner
    yield ingress
    runner.release.set()
    if ingress.state.background_runs:
        await asyncio.gather(*tuple(ingress.state.background_runs), return_exceptions=True)


async def test_a_second_rule_on_one_guest_joins_the_investigation_already_running(
    busy: Ingress,
) -> None:
    """Two rules, one container, one investigation — and five incidents stay five."""
    await _deliver_without_waiting(busy, adguard_oom("first"))
    answer = await _deliver_without_waiting(
        busy, group(vmid=ADGUARD_VMID, alert_name="ContainerUnreachable", delivery="second")
    )

    assert answer.get("joined") is True, (
        f"a second rule firing on the container already under investigation started "
        f"an investigation of its own: {answer}"
    )
    assert len(busy.runner.started) == 1, (
        f"{len(busy.runner.started)} investigations for one failure. The second is "
        f"the same reasoning, at the same cost, by a run that cannot see the first."
    )
    async with busy.gateway.begin(busy.scope) as uow:
        raised = await uow.incidents.query(IncidentQuery(states=(IncidentState.INVESTIGATING,)))
    assert len(raised) == 2, (
        "joining an investigation must not merge the incidents. Two rules fired and "
        "two conditions are true; one investigation covers both."
    )


async def test_the_joined_alert_is_handed_to_the_running_investigation(
    busy: Ingress,
) -> None:
    """The run is told, or joining is just suppression with a nicer name."""
    await _deliver_without_waiting(busy, adguard_oom("first"))
    await _deliver_without_waiting(
        busy, group(vmid=ADGUARD_VMID, alert_name="ContainerUnreachable", delivery="second")
    )

    assert busy.runner.queued, "nothing was handed to the investigation that was joined"
    _, text = busy.runner.queued[0]
    assert "ContainerUnreachable" in text, (
        f"the running investigation was told something arrived and not what: {text!r}"
    )


async def test_a_rule_firing_on_a_different_guest_investigates_for_itself(
    busy: Ingress,
) -> None:
    """Arriving together is not a relation.

    Two containers under one rule is the case resolution was built for, and it
    is the same shape as the unrelated fifth alert in the measured burst: same
    minute, different subject, its own problem.
    """
    await _deliver_without_waiting(busy, adguard_oom("first"))
    answer = await _deliver_without_waiting(busy, clickhouse_storm("second"))

    assert answer.get("joined") is not True, (
        f"an alert about a different container joined the first one's investigation, "
        f"leaving nobody looking at it: {answer}"
    )
    assert len(busy.runner.started) == 2


async def test_two_alerts_arriving_at_once_still_produce_one_investigation(
    busy: Ingress,
) -> None:
    """Alertmanager posts concurrently, and the burst measured here proves it.

    Three of the five deliveries landed inside eighty-two milliseconds of each
    other. An incident becomes joinable only once its run is attached to it, so
    everything between starting the run and attaching it is a window in which a
    second alert sees nothing running and starts its own — and the window used
    to contain an estate write.

    Delivered through ``gather`` rather than in sequence because sequential
    delivery cannot reproduce it: the first request is fully handled before the
    second begins, which is exactly the case that was never in doubt.
    """
    await asyncio.gather(
        _deliver_without_waiting(busy, adguard_oom("first")),
        _deliver_without_waiting(
            busy, group(vmid=ADGUARD_VMID, alert_name="ContainerUnreachable", delivery="second")
        ),
    )

    assert len(busy.runner.started) == 1, (
        f"{len(busy.runner.started)} investigations for two alerts that arrived together "
        f"on one container. An incident whose run exists but is not yet attached to it "
        f"is an incident nothing can join."
    )


async def test_an_alert_arriving_after_the_answer_points_at_it_rather_than_redoing_it(
    ingress: Ingress,
) -> None:
    """The three that arrived fifteen seconds late.

    ``ingress`` rather than ``busy``: the shared runner finishes the moment it
    is awaited, which is exactly the state this is about — the first
    investigation has reported before the second alert lands.
    """
    await deliver(ingress, adguard_oom("first"))
    answer = await deliver(
        ingress, group(vmid=ADGUARD_VMID, alert_name="ContainerUnreachable", delivery="second")
    )

    assert answer.get("joined") is True, (
        f"an alert arriving after the answer started its own investigation: {answer}"
    )
    assert answer.get("answered") is True, (
        "an incident pointed at a finished report must not read as one somebody is looking at now"
    )
    assert len(ingress.runner.started) == 1, (
        f"{len(ingress.runner.started)} investigations. The second re-derived an "
        f"answer that already existed."
    )
    assert ingress.runner.queued == [], "a finished run was handed a message it can never read"
