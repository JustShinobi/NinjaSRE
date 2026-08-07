"""Webhook ingestion: signature verification (SC-003), payload cap, idempotency, dedup linking.

SC-003 requires forgery rejection for all seven sources, so ``webhook_app``
below configures every one of them and ``test_forgery_is_rejected_for_every_source``
/ ``test_a_valid_signature_starts_an_investigation_for_every_source`` are
parametrised across all seven rather than spot-checking two.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable

import pytest
from httpx import ASGITransport, AsyncClient

from config.constants.surfaces import WEBHOOK_MAX_PAYLOAD_BYTES, WEBHOOK_MAX_REQUESTS_PER_TEAM
from gateway.http.app import create_app
from gateway.http.state import GatewayState
from gateway.webhooks.router import WebhookSourceConfig
from gateway.webhooks.verification.hmac import HmacVerifier
from gateway.webhooks.verification.shared_secret import SharedSecretVerifier
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from tests.unit.gateway.http.conftest import ORG, TEAM_PAYMENTS, FakeInvestigationRunner

pytestmark = pytest.mark.asyncio

#: One shared-secret or HMAC secret per source, plus the payload builder and
#: the headers a valid delivery carries. Every source is exercised, not a
#: sample of them (SC-003).
SECRET = "the-real-secret"


def alertmanager_payload() -> dict[str, object]:
    return {
        "receiver": "payments-team",
        "status": "firing",
        "groupKey": "group-1",
        "commonLabels": {"alertname": "HighErrorRate", "severity": "critical"},
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "HighErrorRate",
                    "severity": "critical",
                    "service": "checkout",
                },
                "annotations": {"summary": "checkout error rate above 5%"},
                "startsAt": "2026-08-06T12:00:00Z",
                "endsAt": "0001-01-01T00:00:00Z",
            }
        ],
    }


def pagerduty_payload(event_id: str = "pd-evt-1") -> dict[str, object]:
    return {"event": {"id": event_id, "event_type": "incident.triggered"}, "id": event_id}


def datadog_payload() -> dict[str, object]:
    return {
        "alert_id": "dd-1",
        "alert_title": "High CPU on checkout",
        "alert_transition": "Triggered",
    }


def grafana_payload() -> dict[str, object]:
    return {
        "orgId": 1,
        "ruleName": "HighLatency",
        "state": "alerting",
        "alerts": [
            {
                "labels": {"alertname": "HighLatency"},
                "annotations": {"summary": "p99 latency above 2s"},
            }
        ],
    }


def sentry_payload() -> dict[str, object]:
    return {
        "culprit": "checkout.py",
        "data": {"issue": {"title": "NullPointerException in checkout"}},
    }


def opsgenie_payload() -> dict[str, object]:
    return {"action": "Create", "alert": {"alertId": "og-1", "message": "Disk almost full"}}


def generic_payload() -> dict[str, object]:
    return {"alert_name": "CustomAlert", "summary": "something broke", "severity": "high"}


#: source name -> payload builder, for the seven sources SC-003 names.
PAYLOADS: dict[str, Callable[[], dict[str, object]]] = {
    "alertmanager": alertmanager_payload,
    "pagerduty": pagerduty_payload,
    "datadog": datadog_payload,
    "grafana": grafana_payload,
    "sentry": sentry_payload,
    "opsgenie": opsgenie_payload,
    "generic": generic_payload,
}


def _shared_secret(header: str) -> Callable[[str], SharedSecretVerifier]:
    return lambda secret: SharedSecretVerifier(secret=secret, header=header)


def _hmac(header: str) -> Callable[[str], HmacVerifier]:
    return lambda secret: HmacVerifier(secret=secret, header=header)


#: source name -> verifier factory, matching each vendor's real mechanism (FR-015):
#: PagerDuty, Sentry, and the generic webhook sign with HMAC; the rest carry a
#: shared secret.
VERIFIERS: dict[str, Callable[[str], object]] = {
    "alertmanager": _shared_secret("Authorization"),
    "pagerduty": _hmac("X-PagerDuty-Signature"),
    "datadog": _shared_secret("X-Datadog-Token"),
    "grafana": _shared_secret("Authorization"),
    "sentry": _hmac("Sentry-Hook-Signature"),
    "opsgenie": _shared_secret("Authorization"),
    "generic": _hmac("X-Webhook-Signature"),
}


def valid_headers(source: str, body: bytes) -> dict[str, str]:
    """Return the header a genuine delivery for ``source`` would carry."""
    verifier = VERIFIERS[source](SECRET)
    if isinstance(verifier, HmacVerifier):
        signature = hmac.new(SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return {verifier.header: signature, "Content-Type": "application/json"}
    return {verifier.header: f"Bearer {SECRET}", "Content-Type": "application/json"}


def forged_headers(source: str, body: bytes) -> dict[str, str]:
    """Return a header that will not verify for ``source``."""
    verifier = VERIFIERS[source](SECRET)
    if isinstance(verifier, HmacVerifier):
        forged = hmac.new(b"not-the-real-secret", body, hashlib.sha256).hexdigest()
        return {verifier.header: forged, "Content-Type": "application/json"}
    return {verifier.header: "Bearer not-the-real-secret", "Content-Type": "application/json"}


@pytest.fixture
async def webhook_app() -> tuple[AsyncClient, GatewayState]:
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    state = GatewayState(
        gateway=gateway,
        tokens=TokenService(gateway=gateway),
        investigator=FakeInvestigationRunner(),
    )
    app = create_app(
        state,
        webhook_routes={
            source: (
                WebhookSourceConfig(
                    verifier=factory(SECRET), org_id=ORG, team_node_id=TEAM_PAYMENTS
                ),
            )
            for source, factory in VERIFIERS.items()
        },
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://gateway.test") as client:
        yield client, state


@pytest.mark.parametrize("source", sorted(PAYLOADS))
async def test_a_valid_signature_starts_an_investigation_for_every_source(
    source: str, webhook_app: tuple[AsyncClient, GatewayState]
) -> None:
    """SC-003, the positive case: every source's real mechanism verifies."""
    client, _state = webhook_app
    body = json.dumps(PAYLOADS[source]()).encode("utf-8")
    response = await client.post(
        f"/webhooks/{source}", content=body, headers=valid_headers(source, body)
    )
    assert response.status_code == 202, response.text
    assert response.json()["run_id"]


@pytest.mark.parametrize("source", sorted(PAYLOADS))
async def test_forgery_is_rejected_for_every_source(
    source: str, webhook_app: tuple[AsyncClient, GatewayState]
) -> None:
    """SC-003: a forged signature is rejected for all seven sources."""
    client, _state = webhook_app
    body = json.dumps(PAYLOADS[source]()).encode("utf-8")
    response = await client.post(
        f"/webhooks/{source}", content=body, headers=forged_headers(source, body)
    )
    assert response.status_code == 401
    assert response.json()["error"]["type"] == "unverified"


@pytest.mark.parametrize("source", sorted(PAYLOADS))
async def test_a_missing_signature_is_rejected_for_every_source(
    source: str, webhook_app: tuple[AsyncClient, GatewayState]
) -> None:
    client, _state = webhook_app
    body = json.dumps(PAYLOADS[source]()).encode("utf-8")
    response = await client.post(
        f"/webhooks/{source}", content=body, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 401


async def test_an_oversize_payload_is_rejected_before_verification(
    webhook_app: tuple[AsyncClient, GatewayState],
) -> None:
    client, _state = webhook_app
    oversize = b"x" * (WEBHOOK_MAX_PAYLOAD_BYTES + 1)
    response = await client.post(
        "/webhooks/alertmanager",
        content=oversize,
        headers={"Authorization": f"Bearer {SECRET}", "Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 413


async def test_a_repeated_delivery_is_idempotent(
    webhook_app: tuple[AsyncClient, GatewayState],
) -> None:
    client, state = webhook_app
    body = json.dumps(pagerduty_payload("dup-1")).encode("utf-8")
    headers = valid_headers("pagerduty", body)

    first = await client.post("/webhooks/pagerduty", content=body, headers=headers)
    second = await client.post("/webhooks/pagerduty", content=body, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json().get("duplicate_delivery") is True
    assert len(state.investigator.started) == 1  # type: ignore[attr-defined]


async def test_a_duplicate_alert_within_the_window_is_linked_not_discarded(
    webhook_app: tuple[AsyncClient, GatewayState],
) -> None:
    """FR-018: the second alert links to the first investigation rather than starting a new one."""
    client, state = webhook_app
    first_body = json.dumps(alertmanager_payload()).encode("utf-8")
    first = await client.post(
        "/webhooks/alertmanager",
        content=first_body,
        headers=valid_headers("alertmanager", first_body),
    )

    second_payload = alertmanager_payload()
    second_payload["groupKey"] = "group-2"  # different delivery, same underlying alert
    second_body = json.dumps(second_payload).encode("utf-8")
    second = await client.post(
        "/webhooks/alertmanager",
        content=second_body,
        headers=valid_headers("alertmanager", second_body),
    )

    assert first.json()["linked"] is False
    assert second.json()["linked"] is True
    assert second.json()["run_id"] == first.json()["run_id"]
    assert len(state.investigator.started) == 1  # type: ignore[attr-defined]


async def test_a_resolution_is_linked_to_its_investigation(
    webhook_app: tuple[AsyncClient, GatewayState],
) -> None:
    """FR-019: a resolution event is linked to the originating investigation where one exists."""
    client, state = webhook_app
    firing = alertmanager_payload()
    firing_body = json.dumps(firing).encode("utf-8")
    started = await client.post(
        "/webhooks/alertmanager",
        content=firing_body,
        headers=valid_headers("alertmanager", firing_body),
    )
    run_id = started.json()["run_id"]

    resolved = alertmanager_payload()
    # A resolution is its own delivery, with its own event id — a fresh
    # ``groupKey`` here is what tells it apart from the firing delivery for
    # idempotency, exactly as a real Alertmanager notification would.
    resolved["groupKey"] = "group-1-resolved"
    resolved["status"] = "resolved"
    resolved["alerts"][0]["status"] = "resolved"  # type: ignore[index]
    resolved_body = json.dumps(resolved).encode("utf-8")
    response = await client.post(
        "/webhooks/alertmanager",
        content=resolved_body,
        headers=valid_headers("alertmanager", resolved_body),
    )

    assert response.status_code == 202
    assert response.json() == {"resolution": "linked", "run_id": run_id}


async def test_a_resolution_with_no_matching_investigation_is_recorded_standalone(
    webhook_app: tuple[AsyncClient, GatewayState],
) -> None:
    """FR-019: a resolution with nothing to link to is recorded standalone, not rejected."""
    client, _state = webhook_app
    resolved = alertmanager_payload()
    resolved["groupKey"] = "never-seen-before"
    resolved["status"] = "resolved"
    resolved["alerts"][0]["status"] = "resolved"  # type: ignore[index]
    body = json.dumps(resolved).encode("utf-8")
    response = await client.post(
        "/webhooks/alertmanager", content=body, headers=valid_headers("alertmanager", body)
    )

    assert response.status_code == 202
    assert response.json() == {"resolution": "standalone", "linked": False}


async def test_a_1000_event_storm_is_bounded_with_a_complete_shed_record(
    webhook_app: tuple[AsyncClient, GatewayState],
) -> None:
    """SC-004: 1,000 events in a minute produce bounded investigations, with
    everything shed recorded and reportable through GET /health/ready."""
    client, state = webhook_app

    admitted = 0
    shed = 0
    for index in range(1000):
        payload = generic_payload()
        payload["event_id"] = f"storm-{index}"  # distinct delivery, same underlying alert
        body = json.dumps(payload).encode("utf-8")
        response = await client.post(
            "/webhooks/generic", content=body, headers=valid_headers("generic", body)
        )
        if response.status_code == 429:
            shed += 1
            assert response.json()["shed"] is True
        else:
            assert response.status_code == 202
            admitted += 1

    assert admitted == WEBHOOK_MAX_REQUESTS_PER_TEAM
    assert shed == 1000 - WEBHOOK_MAX_REQUESTS_PER_TEAM

    # Bounded investigations: every admitted delivery names the same alert, so
    # deduplication links all of them to the one investigation it started.
    assert len(state.investigator.started) == 1  # type: ignore[attr-defined]

    # Nothing shed is silent: every one of them is in the log, reportable, and
    # readable from the health endpoint an operator actually looks at.
    shed_records = state.webhook_shedder.log.since(state.webhook_shedder.log.all()[0].occurred_at)
    assert len(shed_records) == shed
    assert all(
        record.source == "generic" and record.team_node_id == TEAM_PAYMENTS
        for record in shed_records
    )

    ready = await client.get("/health/ready")
    assert ready.status_code == 200
    assert len(ready.json()["recent_shedding"]) > 0


__all__: list[str] = []
