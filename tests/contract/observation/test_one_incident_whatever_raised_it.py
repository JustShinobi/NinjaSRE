"""Contract: a webhook alert and a detected condition produce the same kind of incident.

SC-006, and the reason it is a contract test rather than a unit one: the claim
is about two *paths* through the deployment, not about two functions. One goes
through the HTTP webhook route with a signed Alertmanager payload; the other
goes through an evaluation tick over stored signals. Both come out the other
side as incidents, and this file asserts that the two records differ only in the
fields that are supposed to differ.

If they ever diverge, every component downstream — the console, the dispatcher,
the escalation registry, the report — grows a second case, and the second case
is the one nobody tests.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import AsyncIterator
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from gateway.http.app import create_app
from gateway.http.state import GatewayState
from gateway.webhooks.router import WebhookSourceConfig
from gateway.webhooks.verification.hmac import HmacVerifier
from platform.identity.tokens import TokenService
from platform.incidents.detection import DetectionIntake
from platform.incidents.lifecycle import IncidentLifecycle
from platform.notifications.models import Severity
from platform.observation.detectors.model import Condition, ConditionKind, DetectorDeclaration
from platform.observation.evaluation import EvaluationTick
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import (
    Incident,
    IncidentOrigin,
    IncidentQuery,
    IncidentState,
    PersistenceGateway,
    Resource,
    Signal,
    SignalKind,
    TenantScope,
)
from platform.persistence.ports.signal_store import signal_key
from tests.unit.gateway.http.conftest import FakeInvestigationRunner

pytestmark = pytest.mark.contract

ORG = "acme"
TEAM = "team-payments"
SECRET = "a-shared-secret-for-the-contract-suite"

EPOCH = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def at(minutes: float = 0.0) -> datetime:
    """Return a fixed instant offset by ``minutes``."""
    return EPOCH + timedelta(minutes=minutes)


@pytest.fixture
async def deployment() -> AsyncIterator[tuple[AsyncClient, PersistenceGateway]]:
    """Yield a client over the real app and the gateway behind it."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")

    state = GatewayState(
        gateway=store,
        tokens=TokenService(gateway=store),
        investigator=FakeInvestigationRunner(),
    )
    app = create_app(
        state,
        webhook_routes={
            "alertmanager": (
                WebhookSourceConfig(
                    verifier=HmacVerifier(secret=SECRET, header="x-signature", prefix="sha256="),
                    org_id=ORG,
                    team_node_id=TEAM,
                ),
            )
        },
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://deployment") as client:
        yield client, store


def signed(body: bytes) -> dict[str, str]:
    """Return the headers a genuine Alertmanager delivery would carry."""
    digest = hmac.new(SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return {"x-signature": f"sha256={digest}", "content-type": "application/json"}


def alertmanager_payload() -> dict[str, Any]:
    """Return one firing Alertmanager group."""
    return {
        "receiver": "ninjasre",
        "status": "firing",
        "groupKey": "group-contract-1",
        "commonLabels": {"severity": "critical"},
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "DatastoreNearFull",
                    "severity": "critical",
                    "service": "store-cove",
                },
                "annotations": {
                    "summary": "store-cove is 95.65% full",
                    "description": "the datastore crossed ninety per cent and stayed there",
                },
                "startsAt": "2026-03-01T11:55:00Z",
            }
        ],
    }


def near_full() -> DetectorDeclaration:
    """Return the detector the detected half of this test fires."""
    return DetectorDeclaration(
        detector_id="datastore-near-full",
        name="Datastore near full",
        description="A datastore that fills stops every guest on it at once.",
        resource_kinds=("datastore",),
        signal="storage.used_percent",
        condition=Condition(kind=ConditionKind.THRESHOLD, fire_value=90.0, clear_value=80.0),
        for_seconds=300,
        recovery_seconds=300,
        severity=Severity.CRITICAL,
        team_node_id=TEAM,
    )


def sample(minutes: float, value: float) -> Signal:
    """Return one numeric sample about the same datastore."""
    observed_at = at(minutes)
    return Signal(
        signal_id=signal_key("storage.used_percent", "store-cove", observed_at),
        name="storage.used_percent",
        resource_id="store-cove",
        source="poller:proxmox",
        kind=SignalKind.NUMBER,
        observed_at=observed_at,
        value=value,
        interval_seconds=60,
    )


async def ingest_an_alert(client: AsyncClient) -> httpx.Response:
    """Post a signed firing alert and return the acknowledgement."""
    body = json.dumps(alertmanager_payload()).encode("utf-8")
    return await client.post("/webhooks/alertmanager", content=body, headers=signed(body))


async def detect_a_condition(store: PersistenceGateway, *, run_id: str = "run-detected") -> None:
    """Run one evaluation tick that fires, absorb it, and attach its investigation.

    The run is attached here because the ingested half attaches one too, and the
    comparison below is between the two incidents *at the same point in their
    lives*. Comparing a dispatched incident with an undispatched one would find
    a difference that is about when the snapshot was taken rather than about
    which path raised it.
    """
    datastore = Resource(
        resource_id="store-cove", kind="datastore", source="proxmox", native_id="store-cove"
    )
    async with store.begin(TenantScope(org_id=ORG, team_node_id=TEAM)) as uow:
        await uow.signals.append([sample(-5, 91.0), sample(-2, 92.0), sample(0, 95.65)])
        outcome = await EvaluationTick(detectors=(near_full(),)).run(
            uow.signals, resources=(datastore,), now=at()
        )
        lifecycle = IncidentLifecycle(store=uow.incidents)
        report = await DetectionIntake(
            lifecycle=lifecycle,
            detectors={"datastore-near-full": near_full()},
        ).absorb(outcome, resources=(datastore,), now=at())
        for incident in report.opened:
            await lifecycle.attach_run(incident.incident_id, run_id, now=at())


async def incidents_of(store: PersistenceGateway, origin: IncidentOrigin) -> tuple[Incident, ...]:
    """Return the incidents this deployment holds from one origin."""
    async with store.begin(TenantScope(org_id=ORG)) as uow:
        return await uow.incidents.query(IncidentQuery(origins=(origin,)))


# --- SC-006 -------------------------------------------------------------------------


async def test_a_webhook_alert_and_a_detected_condition_are_structurally_identical(
    deployment: tuple[AsyncClient, PersistenceGateway],
) -> None:
    """Every field is populated the same way in both, or differs for a stated reason."""
    client, store = deployment

    acknowledged = await ingest_an_alert(client)
    await detect_a_condition(store)

    assert acknowledged.status_code == 202
    ingested = (await incidents_of(store, IncidentOrigin.ALERT))[0]
    detected = (await incidents_of(store, IncidentOrigin.DETECTOR))[0]

    #: The fields that are *supposed* to differ, and why. Everything else must
    #: agree in kind, which is what "one lifecycle" actually claims.
    expected_to_differ = {
        "incident_id",
        "correlation_key",
        "origin",
        "origin_id",
        "summary",
        "opened_at",
        "subjects",
        "title",
        # Both carry exactly one run; the identifiers differ because they are
        # two different investigations of two different things.
        "run_ids",
    }
    for field in fields(Incident):
        if field.name in expected_to_differ:
            continue
        assert getattr(ingested, field.name) == getattr(detected, field.name), (
            f"{field.name} differs between an ingested alert and a detected condition. "
            f"Every field but {sorted(expected_to_differ)} has to be populated the same "
            f"way, or something downstream will grow a second case."
        )


async def test_both_are_the_same_type_in_the_same_state_at_the_same_severity(
    deployment: tuple[AsyncClient, PersistenceGateway],
) -> None:
    client, store = deployment

    await ingest_an_alert(client)
    await detect_a_condition(store)

    ingested = (await incidents_of(store, IncidentOrigin.ALERT))[0]
    detected = (await incidents_of(store, IncidentOrigin.DETECTOR))[0]

    assert type(ingested) is type(detected) is Incident
    assert ingested.state is detected.state is IncidentState.INVESTIGATING
    assert ingested.severity == detected.severity == "critical"
    assert ingested.team_node_id == detected.team_node_id == TEAM


async def test_both_carry_evidence_and_at_least_one_named_subject(
    deployment: tuple[AsyncClient, PersistenceGateway],
) -> None:
    """Article I applies to an ingested alert exactly as it does to a detected one."""
    client, store = deployment

    await ingest_an_alert(client)
    await detect_a_condition(store)

    for origin in (IncidentOrigin.ALERT, IncidentOrigin.DETECTOR):
        incident = (await incidents_of(store, origin))[0]
        assert incident.subjects, f"an incident from {origin.value} names nothing"
        assert incident.subjects[0].detail, f"an incident from {origin.value} carries no detail"


async def test_both_have_a_timeline_whose_first_entry_says_what_happened(
    deployment: tuple[AsyncClient, PersistenceGateway],
) -> None:
    client, store = deployment

    await ingest_an_alert(client)
    await detect_a_condition(store)

    async with store.begin(TenantScope(org_id=ORG)) as uow:
        for origin in (IncidentOrigin.ALERT, IncidentOrigin.DETECTOR):
            incident = (await uow.incidents.query(IncidentQuery(origins=(origin,))))[0]
            history = await uow.incidents.timeline(incident.incident_id)
            assert history, f"an incident from {origin.value} has no timeline"
            assert history[0].cause, f"an incident from {origin.value} opened without a cause"
            assert history[0].actor, f"an incident from {origin.value} opened without an actor"


# --- The webhook path no longer starts a run without an incident ----------------------


async def test_an_ingested_alert_produces_an_incident_with_its_run_attached(
    deployment: tuple[AsyncClient, PersistenceGateway],
) -> None:
    """The run is attached to the incident rather than standing in for it."""
    client, store = deployment

    acknowledged = await ingest_an_alert(client)
    body = acknowledged.json()

    async with store.begin(TenantScope(org_id=ORG)) as uow:
        incident = await uow.incidents.get(body["incident_id"])

    assert incident is not None
    assert incident.run_ids == (body["run_id"],)
    assert incident.state is IncidentState.INVESTIGATING


async def test_a_resolution_closes_the_incident_the_firing_alert_opened(
    deployment: tuple[AsyncClient, PersistenceGateway],
) -> None:
    client, store = deployment
    opened = (await ingest_an_alert(client)).json()

    resolved = alertmanager_payload()
    resolved["groupKey"] = "group-contract-1-resolved"
    resolved["status"] = "resolved"
    resolved["alerts"][0]["status"] = "resolved"  # type: ignore[index]
    body = json.dumps(resolved).encode("utf-8")
    acknowledged = await client.post("/webhooks/alertmanager", content=body, headers=signed(body))

    async with store.begin(TenantScope(org_id=ORG)) as uow:
        incident = await uow.incidents.get(opened["incident_id"])

    assert acknowledged.json()["incident_id"] == opened["incident_id"]
    assert incident is not None
    assert incident.state is IncidentState.RESOLVED
    assert incident.self_resolved
