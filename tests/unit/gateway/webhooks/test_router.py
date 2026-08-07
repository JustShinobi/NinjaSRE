"""Webhook ingestion: signature verification (SC-003), payload cap, idempotency, dedup linking."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from httpx import ASGITransport, AsyncClient

from config.constants.surfaces import WEBHOOK_MAX_PAYLOAD_BYTES
from gateway.http.app import create_app
from gateway.http.state import GatewayState
from gateway.webhooks.router import WebhookSourceConfig
from gateway.webhooks.verification.hmac import HmacVerifier
from gateway.webhooks.verification.shared_secret import SharedSecretVerifier
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from tests.unit.gateway.http.conftest import ORG, TEAM_PAYMENTS, FakeInvestigationRunner

pytestmark = pytest.mark.asyncio

ALERTMANAGER_SECRET = "am-shared-secret"
PAGERDUTY_SECRET = "pd-hmac-secret"


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
            "alertmanager": (
                WebhookSourceConfig(
                    verifier=SharedSecretVerifier(
                        secret=ALERTMANAGER_SECRET, header="Authorization"
                    ),
                    org_id=ORG,
                    team_node_id=TEAM_PAYMENTS,
                ),
            ),
            "pagerduty": (
                WebhookSourceConfig(
                    verifier=HmacVerifier(secret=PAGERDUTY_SECRET, header="X-PagerDuty-Signature"),
                    org_id=ORG,
                    team_node_id=TEAM_PAYMENTS,
                ),
            ),
        },
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://gateway.test") as client:
        yield client, state


async def test_a_valid_shared_secret_starts_an_investigation(
    webhook_app: tuple[AsyncClient, GatewayState],
) -> None:
    client, state = webhook_app
    response = await client.post(
        "/webhooks/alertmanager",
        json=alertmanager_payload(),
        headers={"Authorization": f"Bearer {ALERTMANAGER_SECRET}"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["run_id"]
    assert body["linked"] is False


async def test_a_forged_shared_secret_is_rejected(
    webhook_app: tuple[AsyncClient, GatewayState],
) -> None:
    """SC-003."""
    client, state = webhook_app
    response = await client.post(
        "/webhooks/alertmanager",
        json=alertmanager_payload(),
        headers={"Authorization": "Bearer not-the-real-secret"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["type"] == "unverified"


async def test_a_missing_signature_is_rejected(
    webhook_app: tuple[AsyncClient, GatewayState],
) -> None:
    client, state = webhook_app
    response = await client.post("/webhooks/alertmanager", json=alertmanager_payload())
    assert response.status_code == 401


async def test_a_valid_hmac_signature_starts_an_investigation(
    webhook_app: tuple[AsyncClient, GatewayState],
) -> None:
    """SC-003, the positive case for HMAC (PagerDuty)."""
    client, state = webhook_app
    payload = pagerduty_payload()
    body = json.dumps(payload).encode("utf-8")
    signature = hmac.new(PAGERDUTY_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()

    response = await client.post(
        "/webhooks/pagerduty",
        content=body,
        headers={"X-PagerDuty-Signature": signature, "Content-Type": "application/json"},
    )
    assert response.status_code == 202
    assert response.json()["run_id"]


async def test_a_forged_hmac_signature_is_rejected(
    webhook_app: tuple[AsyncClient, GatewayState],
) -> None:
    """SC-003."""
    client, state = webhook_app
    payload = pagerduty_payload()
    body = json.dumps(payload).encode("utf-8")
    forged = hmac.new(b"wrong-secret", body, hashlib.sha256).hexdigest()

    response = await client.post(
        "/webhooks/pagerduty",
        content=body,
        headers={"X-PagerDuty-Signature": forged, "Content-Type": "application/json"},
    )
    assert response.status_code == 401


async def test_an_oversize_payload_is_rejected_before_verification(
    webhook_app: tuple[AsyncClient, GatewayState],
) -> None:
    client, state = webhook_app
    oversize = b"x" * (WEBHOOK_MAX_PAYLOAD_BYTES + 1)
    response = await client.post(
        "/webhooks/alertmanager",
        content=oversize,
        headers={
            "Authorization": f"Bearer {ALERTMANAGER_SECRET}",
            "Content-Type": "application/octet-stream",
        },
    )
    assert response.status_code == 413


async def test_a_repeated_delivery_is_idempotent(
    webhook_app: tuple[AsyncClient, GatewayState],
) -> None:
    client, state = webhook_app
    body = json.dumps(pagerduty_payload("dup-1")).encode("utf-8")
    signature = hmac.new(PAGERDUTY_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
    headers = {"X-PagerDuty-Signature": signature, "Content-Type": "application/json"}

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
    first = await client.post(
        "/webhooks/alertmanager",
        json=alertmanager_payload(),
        headers={"Authorization": f"Bearer {ALERTMANAGER_SECRET}"},
    )
    second_payload = alertmanager_payload()
    second_payload["groupKey"] = "group-2"  # different delivery, same underlying alert
    second = await client.post(
        "/webhooks/alertmanager",
        json=second_payload,
        headers={"Authorization": f"Bearer {ALERTMANAGER_SECRET}"},
    )

    assert first.json()["linked"] is False
    assert second.json()["linked"] is True
    assert second.json()["run_id"] == first.json()["run_id"]
    assert len(state.investigator.started) == 1  # type: ignore[attr-defined]
