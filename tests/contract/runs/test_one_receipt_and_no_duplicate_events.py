"""Characterisation: an alert-triggered investigation leaves one receipt, no duplicate event.

This must pass **before** this feature's changes as much as after — it is the
net that catches duplication that composing the recorder could introduce, not
a new behaviour. Composed against ``UnconfiguredInvestigator``, the runtime
this deployment runs today whenever nothing was named, so this exercises the
one writer that exists in production right now:
``gateway.http.orchestration.start_investigation``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from gateway.http.asgi import UnconfiguredInvestigator
from gateway.http.orchestration import start_investigation
from gateway.http.state import GatewayState
from platform.identity.tokens import TokenService
from platform.incidents.lifecycle import IncidentLifecycle, IncidentRaise
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.incident_store import IncidentOrigin, IncidentSubject
from platform.persistence.ports.transaction import TenantScope

pytestmark = pytest.mark.contract

ORG = "acme"


@pytest.fixture
async def gateway() -> FakePersistence:
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    return store


async def test_one_alert_triggered_investigation_leaves_exactly_one_receipt(
    gateway: FakePersistence,
) -> None:
    scope = TenantScope(org_id=ORG, team_node_id="platform")
    async with gateway.begin(scope) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        incident = await lifecycle.raise_incident(
            IncidentRaise(
                correlation_key="alert:instance-down:host-1",
                title="InstanceDown",
                summary="host-1 stopped responding",
                origin=IncidentOrigin.ALERT,
                origin_id="alertmanager",
                severity="critical",
                subjects=(IncidentSubject(resource_id="host-1"),),
            ),
            now=datetime(2026, 3, 1, 9, 0, tzinfo=UTC),
        )

    state = GatewayState(
        gateway=gateway,
        tokens=TokenService(gateway=gateway),
        investigator=UnconfiguredInvestigator(),
    )

    await start_investigation(
        state,
        scope=scope,
        trigger="alert",
        objective="host-1 is down",
        principal_id="alertmanager",
        alert_source="alertmanager",
        incident_id=incident.incident_id,
        alert_labels={"alertname": "InstanceDown"},
        credential_name="delivery token am-cluster",
    )
    # The background task the route/webhook never awaits raises against the
    # stand-in investigator; give it a turn to run and fail before reading.
    import asyncio

    await asyncio.sleep(0)

    async with gateway.begin(scope) as uow:
        history = await IncidentLifecycle(store=uow.incidents).timeline(incident.incident_id)

    from platform.persistence.ports.incident_store import TimelineKind

    receipts = [entry for entry in history if entry.kind is TimelineKind.ALERT_RECEIVED]
    assert len(receipts) == 1


async def test_no_event_in_the_runs_log_appears_twice(gateway: FakePersistence) -> None:
    scope = TenantScope(org_id=ORG, team_node_id="platform")
    state = GatewayState(
        gateway=gateway,
        tokens=TokenService(gateway=gateway),
        investigator=UnconfiguredInvestigator(),
    )

    run_id = await start_investigation(
        state,
        scope=scope,
        trigger="alert",
        objective="host-1 is down",
        principal_id="alertmanager",
        alert_source="alertmanager",
    )
    import asyncio

    await asyncio.sleep(0)

    async with gateway.begin(scope) as uow:
        events = await uow.run_traces.events_for_run(run_id)

    keys = [(event.kind, event.sequence) for event in events]
    assert len(keys) == len(set(keys)), f"a run event was recorded more than once: {keys}"
