"""From an Alertmanager delivery to an estate resource, and to a finding when it is not.

The webhook already raised an incident and started an investigation. What is
asserted here is the step this feature adds between the two: the alert's labels
are resolved against the estate, so the incident points at a resource rather
than at a label value, the investigation starts knowing what it is about, and a
target this estate does not hold is stored and readable instead of dropped.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from config.constants.runs import TRIGGER_ALERT
from gateway.http.app import create_app
from gateway.http.state import GatewayState
from gateway.webhooks.router import WebhookSourceConfig
from gateway.webhooks.verification.shared_secret import SharedSecretVerifier
from platform.estate.alert_resolution import UNRESOLVED_TARGET_PREFIX
from platform.identity.permissions import Role
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.config_repository import ConfigNode, ConfigNodeKind
from platform.persistence.ports.estate_repository import ReferenceKind, Resource
from platform.persistence.ports.incident_store import IncidentQuery
from platform.persistence.ports.transaction import TenantScope
from platform.runs.recorder import RecordedCall, RecordedTurn, RunRecorder
from tests.unit.gateway.http.conftest import (
    ORG,
    TEAM_PAYMENTS,
    FakeInvestigationRunner,
    issue_token,
)

pytestmark = pytest.mark.asyncio

SECRET = "alertmanager-delivery-secret"
ADGUARD = "proxmox:container/hal9000/110"


@dataclass(slots=True)
class Ingress:
    """A deployment whose Alertmanager path verifies, with an estate behind it."""

    client: AsyncClient
    state: GatewayState
    gateway: FakePersistence
    runner: FakeInvestigationRunner
    token: str

    @property
    def scope(self) -> TenantScope:
        return TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)


def container(
    vmid: int,
    *,
    name: str,
    address: str,
    zone: str,
    domain: str = "",
) -> Resource:
    """Return a swept container carrying what 053's enrichment writes onto one."""
    attributes: dict[str, Any] = {"vmid": vmid, "address": address, "zone": zone}
    if domain:
        attributes["domain"] = domain
    return Resource(
        resource_id=f"proxmox:container/hal9000/{vmid}",
        kind="container",
        source="proxmox",
        native_id=f"container/hal9000/{vmid}",
        display_name=name,
        team_node_id=TEAM_PAYMENTS,
        attributes=attributes,
    )


def firing(labels: dict[str, str], *, group_key: str = "group-1") -> dict[str, Any]:
    """Return an Alertmanager group in the shape the cluster's own sends."""
    return {
        "receiver": "ninjasre",
        "status": "firing",
        "groupKey": group_key,
        "commonLabels": {"alertname": "ContainerMemoryHigh", "severity": "critical"},
        "alerts": [
            {
                "status": "firing",
                "labels": {"alertname": "ContainerMemoryHigh", "severity": "critical", **labels},
                "annotations": {"summary": "memory usage above 90% for ten minutes"},
                "startsAt": "2026-08-10T12:00:00Z",
                "endsAt": "0001-01-01T00:00:00Z",
            }
        ],
    }


@pytest.fixture
async def ingress() -> AsyncIterator[Ingress]:
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    scope = TenantScope(org_id=ORG, team_node_id=TEAM_PAYMENTS)
    async with gateway.begin(TenantScope(org_id=ORG)) as uow:
        await uow.config.upsert(
            ConfigNode(
                node_id=TEAM_PAYMENTS, kind=ConfigNodeKind.TEAM, name=TEAM_PAYMENTS, parent_id=ORG
            )
        )
    async with gateway.begin(scope) as uow:
        await uow.estate.upsert(
            container(110, name="adguard", address="10.20.20.10", zone="apps", domain="dns.hal")
        )
        await uow.estate.upsert(
            container(111, name="clickhouse", address="10.20.20.11", zone="apps")
        )

    tokens = TokenService(gateway=gateway)
    runner = FakeInvestigationRunner()
    state = GatewayState(gateway=gateway, tokens=tokens, investigator=runner)
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
    token = await issue_token(
        gateway, tokens, user_id="viewer", role=Role.VIEWER, node_id=TEAM_PAYMENTS
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://gateway.test") as client:
        yield Ingress(client=client, state=state, gateway=gateway, runner=runner, token=token)


async def deliver(ingress: Ingress, payload: dict[str, Any]) -> dict[str, Any]:
    """Post ``payload`` as a verified Alertmanager delivery and drain the run."""
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


async def test_a_resolved_alert_makes_the_incident_point_at_the_resource(
    ingress: Ingress,
) -> None:
    """The incident's subject is an estate identifier, not a label value."""
    await deliver(ingress, firing({"vmid": "110", "instance": "10.20.10.1:9221"}))

    async with ingress.gateway.begin(ingress.scope) as uow:
        incidents = await uow.incidents.query(IncidentQuery(limit=10))

    assert len(incidents) == 1
    assert incidents[0].subject_ids == (ADGUARD,)
    evidence = incidents[0].subjects[0].evidence
    assert evidence["matched_on"] == "vmid"
    assert evidence["target"] == "110"
    assert evidence["zone"] == "apps"


async def test_the_investigation_starts_knowing_which_resource_it_is_about(
    ingress: Ingress,
) -> None:
    """The agent's first capability call needs the identifier, not the label."""
    await deliver(ingress, firing({"vmid": "110"}))

    assert len(ingress.runner.started) == 1
    context = ingress.runner.started[0].context
    assert context["resource_id"] == ADGUARD
    assert context["resource_kind"] == "container"
    assert context["resource_zone"] == "apps"


async def test_the_resource_records_the_incident_that_named_it(ingress: Ingress) -> None:
    """The resource page shows what happened to it, which is why resolution exists."""
    await deliver(ingress, firing({"vmid": "110"}))

    async with ingress.gateway.begin(ingress.scope) as uow:
        references = await uow.estate.references(ADGUARD, limit=10)

    kinds = {reference.reference_kind for reference in references}
    assert ReferenceKind.INCIDENT in kinds
    assert ReferenceKind.RUN in kinds


async def test_an_unknown_target_is_stored_on_the_incident_rather_than_dropped(
    ingress: Ingress,
) -> None:
    """A finding, in the same sense 053's reconciliation divergence is one."""
    await deliver(ingress, firing({"instance": "10.20.20.99:9100"}, group_key="group-2"))

    async with ingress.gateway.begin(ingress.scope) as uow:
        incidents = await uow.incidents.query(IncidentQuery(limit=10))

    subject = next(
        subject
        for subject in incidents[0].subjects
        if subject.resource_id.startswith(UNRESOLVED_TARGET_PREFIX)
    )
    assert subject.evidence["target"] == "10.20.20.99"
    assert subject.evidence["zone"] == "apps"
    assert "no resource in this estate reports that address" in subject.detail


async def test_an_unknown_target_is_readable_over_the_api(ingress: Ingress) -> None:
    """Stored is not enough: acceptance asks for a finding instead of silence."""
    await deliver(ingress, firing({"instance": "10.20.20.99:9100"}, group_key="group-2"))

    response = await ingress.client.get(
        "/v1/estate/unresolved-alert-targets",
        headers={"Authorization": f"Bearer {ingress.token}"},
    )
    assert response.status_code == 200, response.text
    targets = response.json()["targets"]
    assert [entry["value"] for entry in targets] == ["10.20.20.99"]
    assert targets[0]["label"] == "instance"
    assert targets[0]["zone"] == "apps"
    assert targets[0]["alert_name"] == "ContainerMemoryHigh"
    assert targets[0]["incident_id"]


async def test_an_estate_that_resolves_the_alert_reports_no_unresolved_target(
    ingress: Ingress,
) -> None:
    """The listing is findings, not a log of every delivery."""
    await deliver(ingress, firing({"vmid": "110"}))

    response = await ingress.client.get(
        "/v1/estate/unresolved-alert-targets",
        headers={"Authorization": f"Bearer {ingress.token}"},
    )
    assert response.json()["targets"] == []


async def test_the_run_the_alert_started_replays_from_its_own_recorded_events(
    ingress: Ingress,
) -> None:
    """Acceptance 6, against the route the specification names.

    The whole path: an alert creates a run, the run records what it did, and
    ``GET /v1/runs/{run_id}/replay`` reconstructs it from the stored events
    alone. The investigation body is the suite's stand-in — what is being
    asserted is that a run *created by the alert path* is reachable and
    reproducible through the ordinary route, which nothing before this feature
    had a reason to check.
    """
    started = await deliver(ingress, firing({"vmid": "110"}))
    run_id = started["run_id"]

    async with ingress.gateway.begin(ingress.scope) as uow:
        recorder = RunRecorder(store=uow.run_traces)
        turn = await recorder.record_turn(
            RecordedTurn(
                run_id=run_id,
                index=0,
                model="scenario-1",
                selection_rationale="the alert names a guest, so start at the hypervisor",
                offered_capabilities=("proxmox_guest_state",),
            )
        )
        await recorder.record_call(
            RecordedCall(
                run_id=run_id,
                turn_id=turn.turn_id,
                name="proxmox_guest_state",
                arguments={"vmid": "110"},
                result={"status": "running", "restarts": 2},
            )
        )

    response = await ingress.client.get(
        f"/v1/runs/{run_id}/replay", headers={"Authorization": f"Bearer {ingress.token}"}
    )

    assert response.status_code == 200, response.text
    replayed = response.json()
    assert replayed["run_id"] == run_id
    assert [call["name"] for turn in replayed["turns"] for call in turn["calls"]] == [
        "proxmox_guest_state"
    ]
    assert not replayed["is_interrupted"]


async def test_the_replayed_run_is_the_one_the_alert_created(ingress: Ingress) -> None:
    """The run is keyed by the alert's own fingerprint, so the two are one thing."""
    started = await deliver(ingress, firing({"vmid": "110"}))

    async with ingress.gateway.begin(ingress.scope) as uow:
        run = await uow.run_traces.get_run(started["run_id"])

    assert run is not None
    assert run.trigger == TRIGGER_ALERT
    assert run.alert_id
