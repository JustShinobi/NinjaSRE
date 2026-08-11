"""The rules decide what happens to a verified delivery, and the ledger says which one.

The seam this feature moves. Verification still decides *who*; a rule now
decides *what*, and the default rule set reproduces what the handler did before
rules existed — which is what
``test_post_verification_behaviour.py`` pins from the other side.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from httpx import AsyncClient

from gateway.http.state import GatewayState
from platform.config_service.service import ConfigService
from platform.persistence.ports import (
    IncidentQuery,
    TenantScope,
    TransitOutcome,
    TransitQuery,
)
from tests.unit.gateway.http.conftest import ORG, TEAM_PAYMENTS, FakeInvestigationRunner
from tests.unit.gateway.webhooks.test_router import (
    alertmanager_payload,
    valid_headers,
    webhook_app,  # noqa: F401 — the fixture this module runs against
)

pytestmark = pytest.mark.asyncio


def _started(state: GatewayState) -> list[object]:
    """Return the investigations the fake runner was asked to start."""
    runner = state.investigator
    assert isinstance(runner, FakeInvestigationRunner)
    return list(runner.started)


async def configure(state: GatewayState, rules: list[dict[str, Any]]) -> None:
    """Store ``rules`` as the organisation's transit rule set."""
    service = ConfigService(gateway=state.gateway, scope=TenantScope(org_id=ORG))
    await service.set_settings(ORG, {"transit": {"rules": rules}}, actor_id="tester")


async def deliver(client: AsyncClient, payload: dict[str, object] | None = None) -> Any:
    """Post one genuine Alertmanager delivery and return the acknowledgement."""
    body = json.dumps(payload if payload is not None else alertmanager_payload()).encode("utf-8")
    response = await client.post(
        "/webhooks/alertmanager", content=body, headers=valid_headers("alertmanager", body)
    )
    return response


async def test_a_discarding_rule_stops_the_investigation_and_leaves_the_reason(
    webhook_app: tuple[AsyncClient, GatewayState],  # noqa: F811
) -> None:
    """Discard is always discard-with-reason, and a discarded delivery still ledgers."""
    client, state = webhook_app
    await configure(
        state,
        [
            {
                "rule_id": "alertmanager-is-noisy",
                "sources": ["alertmanager"],
                "action": "discard",
                "reason": "this receiver is being decommissioned",
            },
            {"rule_id": "everything-else", "action": "investigate"},
        ],
    )

    response = await deliver(client)

    assert response.status_code == 202
    assert response.json()["discarded"] is True
    assert _started(state) == []

    async with state.gateway.begin(TenantScope(org_id=ORG)) as uow:
        rows = await uow.transit.deliveries(TransitQuery())
        incidents = await uow.incidents.query(IncidentQuery())

    assert rows[0].outcome is TransitOutcome.DISCARDED
    assert rows[0].reason == "this receiver is being decommissioned"
    assert rows[0].matched_rule == "alertmanager-is-noisy"
    assert incidents == ()


async def test_a_record_only_rule_raises_the_incident_and_starts_nothing(
    webhook_app: tuple[AsyncClient, GatewayState],  # noqa: F811
) -> None:
    client, state = webhook_app
    await configure(
        state,
        [
            {"rule_id": "just-file-it", "sources": ["alertmanager"], "action": "record_only"},
            {"rule_id": "everything-else", "action": "investigate"},
        ],
    )

    response = await deliver(client)

    assert response.json()["recorded_only"] is True
    assert _started(state) == []

    async with state.gateway.begin(TenantScope(org_id=ORG)) as uow:
        rows = await uow.transit.deliveries(TransitQuery())
        incidents = await uow.incidents.query(IncidentQuery())

    assert rows[0].outcome is TransitOutcome.RECORDED
    assert len(incidents) == 1
    assert incidents[0].run_ids == ()


async def test_a_rule_can_send_a_delivery_to_a_team_other_than_the_verifier_s(
    webhook_app: tuple[AsyncClient, GatewayState],  # noqa: F811
) -> None:
    """Verification and routing stop being one decision, which is the point."""
    client, state = webhook_app
    await configure(
        state,
        [
            {"rule_id": "to-platform", "sources": ["alertmanager"], "team": "platform"},
            {"rule_id": "everything-else", "action": "investigate"},
        ],
    )

    await deliver(client)

    async with state.gateway.begin(TenantScope(org_id=ORG)) as uow:
        rows = await uow.transit.deliveries(TransitQuery())
        incidents = await uow.incidents.query(IncidentQuery())

    assert rows[0].team_node_id == "platform"
    assert incidents[0].team_node_id == "platform"


async def test_the_catch_all_catches_what_no_rule_named(
    webhook_app: tuple[AsyncClient, GatewayState],  # noqa: F811
) -> None:
    client, state = webhook_app
    await configure(
        state,
        [
            {"rule_id": "only-sentry", "sources": ["sentry"], "action": "discard", "reason": "no"},
            {"rule_id": "everything-else", "action": "investigate"},
        ],
    )

    response = await deliver(client)

    assert response.json()["run_id"]
    async with state.gateway.begin(TenantScope(org_id=ORG)) as uow:
        rows = await uow.transit.deliveries(TransitQuery())

    assert rows[0].matched_rule == "everything-else"
    assert rows[0].team_node_id == TEAM_PAYMENTS


async def test_a_deployment_that_configures_nothing_names_the_default_rule(
    webhook_app: tuple[AsyncClient, GatewayState],  # noqa: F811
) -> None:
    """Today's behaviour, stated as a rule rather than as an absence of them."""
    client, state = webhook_app

    await deliver(client)

    async with state.gateway.begin(TenantScope(org_id=ORG)) as uow:
        rows = await uow.transit.deliveries(TransitQuery())

    assert rows[0].matched_rule == "catch-all"
    assert rows[0].outcome is TransitOutcome.ACCEPTED
