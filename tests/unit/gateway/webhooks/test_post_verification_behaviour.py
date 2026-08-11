"""Characterisation: what a verified delivery does *after* verification, today.

Written before 062 moves the seam, and unchanged afterwards. Verification and
team routing are one decision in this build (``WebhookSourceConfig``), and
everything after it is implicit: a verified delivery goes to the verifier's
team, raises an incident, and starts an investigation. There is no rule, so
there is nothing to read that says so — which is exactly why it is written down
here before anything moves.

These assertions are the contract the default rule set has to reproduce. If
introducing ordered rules changes any of them, the rules are wrong.
"""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

from gateway.http.state import GatewayState
from platform.persistence.ports import IncidentQuery, TenantScope
from tests.unit.gateway.http.conftest import ORG, TEAM_PAYMENTS
from tests.unit.gateway.webhooks.test_router import (
    alertmanager_payload,
    valid_headers,
    webhook_app,  # noqa: F401 — the fixture this module runs against
)

pytestmark = pytest.mark.asyncio


async def _deliver(client: AsyncClient) -> dict[str, object]:
    """Post one genuine Alertmanager delivery and return the acknowledgement."""
    body = json.dumps(alertmanager_payload()).encode("utf-8")
    response = await client.post(
        "/webhooks/alertmanager", content=body, headers=valid_headers("alertmanager", body)
    )
    assert response.status_code == 202, response.text
    answer: dict[str, object] = response.json()
    return answer


async def test_a_verified_delivery_starts_an_investigation(
    webhook_app: tuple[AsyncClient, GatewayState],  # noqa: F811
) -> None:
    """The implicit action, today: every verified delivery is investigated."""
    client, state = webhook_app

    answer = await _deliver(client)

    assert answer["run_id"]
    assert len(state.investigator.started) == 1  # type: ignore[attr-defined]


async def test_a_verified_delivery_raises_an_incident(
    webhook_app: tuple[AsyncClient, GatewayState],  # noqa: F811
) -> None:
    client, state = webhook_app

    answer = await _deliver(client)

    async with state.gateway.begin(TenantScope(org_id=ORG)) as uow:
        incidents = await uow.incidents.query(IncidentQuery())

    assert [incident.incident_id for incident in incidents] == [answer["incident_id"]]


async def test_the_delivery_goes_to_the_team_that_verified_it(
    webhook_app: tuple[AsyncClient, GatewayState],  # noqa: F811
) -> None:
    """The implicit target, today: routing and authentication are one decision."""
    client, state = webhook_app

    await _deliver(client)

    async with state.gateway.begin(TenantScope(org_id=ORG)) as uow:
        incidents = await uow.incidents.query(IncidentQuery())

    assert [incident.team_node_id for incident in incidents] == [TEAM_PAYMENTS]


async def test_the_run_is_attached_to_the_incident_the_alert_raised(
    webhook_app: tuple[AsyncClient, GatewayState],  # noqa: F811
) -> None:
    client, state = webhook_app

    answer = await _deliver(client)

    async with state.gateway.begin(TenantScope(org_id=ORG)) as uow:
        incident = await uow.incidents.get(str(answer["incident_id"]))

    assert incident is not None
    assert list(incident.run_ids) == [answer["run_id"]]
