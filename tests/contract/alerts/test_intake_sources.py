"""What arrives at the webhook boundary: exactly the sources this deployment
still delivers alerts from.

Four sources existed by catalogue rather than by anything in this operator's
environment, and kept four public, authenticated addresses open for traffic
nobody could ever send. This suite is the insurance policy on their removal:
the declared set is exactly three, the four retired addresses answer as
addresses that do not exist — not as a signature failure, not as a server
error — and the three kept sources still authenticate and start an
investigation exactly as they did before.
"""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.http.app import create_app
from gateway.http.state import GatewayState
from gateway.webhooks.router import PROFILES, WebhookSourceConfig
from gateway.webhooks.verification.shared_secret import SharedSecretVerifier
from platform.identity.tokens import TokenService
from platform.persistence.fakes import FakePersistence
from tests.unit.gateway.http.conftest import ORG, TEAM_PAYMENTS, FakeInvestigationRunner

pytestmark = [pytest.mark.contract, pytest.mark.asyncio]

#: The three sources this deployment still delivers alerts from. The only
#: literal list this module authorises — everywhere else, the declared set is
#: read, never restated.
INTAKE_SOURCES: tuple[str, ...] = ("alertmanager", "generic", "grafana")

#: Retired: no longer an address this deployment answers at all.
RETIRED_SOURCES: tuple[str, ...] = ("datadog", "opsgenie", "pagerduty", "sentry")

SECRET = "the-real-secret"


def _payload_for(source: str) -> dict[str, object]:
    if source == "alertmanager":
        return {
            "receiver": "payments-team",
            "status": "firing",
            "groupKey": "group-1",
            "commonLabels": {"alertname": "HighErrorRate", "severity": "critical"},
            "alerts": [
                {
                    "status": "firing",
                    "labels": {"alertname": "HighErrorRate", "severity": "critical"},
                    "annotations": {"summary": "checkout error rate above 5%"},
                    "startsAt": "2026-08-06T12:00:00Z",
                    "endsAt": "0001-01-01T00:00:00Z",
                }
            ],
        }
    if source == "grafana":
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
    return {"alert_name": "CustomAlert", "summary": "something broke", "severity": "high"}


def test_the_declared_intake_sources_are_exactly_three() -> None:
    """The webhook boundary answers for alertmanager, grafana, generic — and nothing else."""
    assert set(PROFILES) == set(INTAKE_SOURCES)


@pytest.fixture
async def unverified_app() -> tuple[AsyncClient, GatewayState]:
    """A deployment with no team wired to any source — every real address still
    exists and answers 401 (nothing verifies it), which is what distinguishes
    it from an address this product no longer has at all."""
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    state = GatewayState(
        gateway=gateway,
        tokens=TokenService(gateway=gateway),
        investigator=FakeInvestigationRunner(),
    )
    app = create_app(state)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://gateway.test") as client:
        yield client, state


@pytest.mark.parametrize("source", RETIRED_SOURCES)
async def test_a_retired_source_address_no_longer_exists(
    source: str, unverified_app: tuple[AsyncClient, GatewayState]
) -> None:
    """The address is gone — a routing 404, not an auth or server failure."""
    client, _state = unverified_app
    response = await client.post(
        f"/webhooks/{source}",
        content=json.dumps(_payload_for("generic")).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 404


@pytest.mark.parametrize("source", INTAKE_SOURCES)
async def test_a_kept_source_address_still_exists(
    source: str, unverified_app: tuple[AsyncClient, GatewayState]
) -> None:
    """A kept address is still real — unverified without a configured route, never absent."""
    client, _state = unverified_app
    response = await client.post(
        f"/webhooks/{source}",
        content=json.dumps(_payload_for(source)).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 401


@pytest.fixture
async def verified_app() -> tuple[AsyncClient, GatewayState]:
    """A deployment with a team wired to each of the three kept sources, by a
    shared secret in ``Authorization`` — the same mechanism alertmanager and
    grafana already used before the cut."""
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
                    verifier=SharedSecretVerifier(secret=SECRET, header="Authorization"),
                    org_id=ORG,
                    team_node_id=TEAM_PAYMENTS,
                ),
            )
            for source in INTAKE_SOURCES
        },
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://gateway.test") as client:
        yield client, state


@pytest.mark.parametrize("source", INTAKE_SOURCES)
async def test_a_kept_source_still_accepts_its_real_delivery_unchanged(
    source: str, verified_app: tuple[AsyncClient, GatewayState]
) -> None:
    """Characterisation: this has to pass before the cut and keep
    passing after it — the same body, the same secret, the same result."""
    client, _state = verified_app
    body = json.dumps(_payload_for(source)).encode("utf-8")
    response = await client.post(
        f"/webhooks/{source}",
        content=body,
        headers={"Authorization": f"Bearer {SECRET}", "Content-Type": "application/json"},
    )
    assert response.status_code == 202, response.text
    assert response.json()["run_id"]


@pytest.mark.parametrize("source", INTAKE_SOURCES)
async def test_a_kept_source_still_rejects_a_forged_delivery_unchanged(
    source: str, verified_app: tuple[AsyncClient, GatewayState]
) -> None:
    """Characterisation, the negative half: a forged secret is still refused."""
    client, _state = verified_app
    body = json.dumps(_payload_for(source)).encode("utf-8")
    response = await client.post(
        f"/webhooks/{source}",
        content=body,
        headers={"Authorization": "Bearer not-the-real-secret", "Content-Type": "application/json"},
    )
    assert response.status_code == 401
