"""The incident and approval stores, tapped at the gateway root — not the call site.

Fakes stand in for `IncidentStore`/`ApprovalStore` so the decorator's own logic
(which write counts as "opened", which as "closed", which as "proposed",
"decided", or "expired") is under test without a database.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from platform.persistence.deployment_taps import (
    _EventPublishingApprovalStore,
    _EventPublishingIncidentStore,
    with_deployment_events,
)
from platform.persistence.ports.approval_store import ApprovalRequest, ApprovalState
from platform.persistence.ports.incident_store import (
    Incident,
    IncidentOrigin,
    IncidentState,
    IncidentSubject,
)
from platform.runs.deployment import DeploymentEventBroker, DeploymentEventKind, DeploymentScope

pytestmark = pytest.mark.asyncio

_NOW = datetime(2026, 8, 27, tzinfo=UTC)


def _incident(
    *, incident_id: str, state: IncidentState, closed_at: datetime | None = None
) -> Incident:
    return Incident(
        incident_id=incident_id,
        correlation_key=f"key-{incident_id}",
        title="a storage pool is unreachable",
        summary="three CIFS mounts stopped answering",
        origin=IncidentOrigin.DETECTOR,
        origin_id="detector-storage",
        severity="high",
        state=state,
        opened_at=_NOW,
        subjects=(IncidentSubject(resource_id="storage/pool-1"),),
        closed_at=closed_at,
        public_id=f"pub-{incident_id}",
    )


class _FakeIncidentStore:
    """The two methods the decorator calls, backed by a dict — nothing else."""

    def __init__(self) -> None:
        self._rows: dict[str, Incident] = {}

    async def get(self, incident_id: str) -> Incident | None:
        return self._rows.get(incident_id)

    async def upsert(self, incident: Incident) -> Incident:
        self._rows[incident.incident_id] = incident
        return incident


def _approval(*, approval_id: str, state: ApprovalState = ApprovalState.PENDING) -> ApprovalRequest:
    return ApprovalRequest(
        approval_id=approval_id,
        run_id="run-1",
        action="remediation.restart",
        side_effect_level="write",
        summary="restart the checkout deployment",
        requested_at=_NOW,
        expires_at=_NOW + timedelta(minutes=30),
        state=state,
    )


class _FakeApprovalStore:
    """The three write methods the decorator calls, backed by a dict."""

    def __init__(self) -> None:
        self._rows: dict[str, ApprovalRequest] = {}

    async def create_request(self, request: ApprovalRequest) -> ApprovalRequest:
        self._rows[request.approval_id] = request
        return request

    async def decide(
        self,
        approval_id: str,
        *,
        state: ApprovalState,
        decided_by: str,
        decided_at: datetime,
        reason: str | None = None,
    ) -> ApprovalRequest:
        from dataclasses import replace

        current = self._rows[approval_id]
        decided = replace(
            current, state=state, decided_by=decided_by, decided_at=decided_at, reason=reason
        )
        self._rows[approval_id] = decided
        return decided

    async def expire_due(self, now: datetime) -> tuple[ApprovalRequest, ...]:
        from dataclasses import replace

        due = [
            row
            for row in self._rows.values()
            if row.state is ApprovalState.PENDING and row.expires_at <= now
        ]
        expired = tuple(replace(row, state=ApprovalState.EXPIRED, decided_at=now) for row in due)
        for row in expired:
            self._rows[row.approval_id] = row
        return expired


# --- Incidents ------------------------------------------------------------------


async def test_a_brand_new_incident_publishes_opened() -> None:
    events = DeploymentEventBroker()
    store = _EventPublishingIncidentStore(_FakeIncidentStore(), events)
    subscription, _ = events.attach()

    await store.upsert(_incident(incident_id="inc-1", state=IncidentState.OPEN))

    delivered = [event async for event in subscription.drain()]
    assert [(event.scope, event.kind, dict(event.payload)) for event in delivered] == [
        (DeploymentScope.INCIDENT, DeploymentEventKind.INCIDENT_OPENED, {"incident_id": "inc-1"})
    ]


async def test_closing_a_live_incident_publishes_closed() -> None:
    events = DeploymentEventBroker()
    inner = _FakeIncidentStore()
    store = _EventPublishingIncidentStore(inner, events)
    await store.upsert(_incident(incident_id="inc-1", state=IncidentState.OPEN))
    subscription, _ = events.attach()

    await store.upsert(_incident(incident_id="inc-1", state=IncidentState.RESOLVED, closed_at=_NOW))

    delivered = [event async for event in subscription.drain()]
    assert [(event.scope, event.kind, dict(event.payload)) for event in delivered] == [
        (DeploymentScope.INCIDENT, DeploymentEventKind.INCIDENT_CLOSED, {"incident_id": "inc-1"})
    ]


async def test_a_transition_between_two_live_states_publishes_nothing() -> None:
    events = DeploymentEventBroker()
    inner = _FakeIncidentStore()
    store = _EventPublishingIncidentStore(inner, events)
    await store.upsert(_incident(incident_id="inc-1", state=IncidentState.OPEN))
    subscription, _ = events.attach()

    # A state change that is not a close — the fake models this as writing
    # OPEN again, which is the same live-to-live case a triage transition is.
    await store.upsert(_incident(incident_id="inc-1", state=IncidentState.OPEN))

    delivered = [event async for event in subscription.drain()]
    assert delivered == []


async def test_reads_pass_through_the_decorator_untouched() -> None:
    events = DeploymentEventBroker()
    inner = _FakeIncidentStore()
    store = _EventPublishingIncidentStore(inner, events)
    written = await store.upsert(_incident(incident_id="inc-1", state=IncidentState.OPEN))

    found = await store.get("inc-1")
    assert found == written


# --- Decisions --------------------------------------------------------------


async def test_creating_a_request_publishes_decision_proposed() -> None:
    events = DeploymentEventBroker()
    store = _EventPublishingApprovalStore(_FakeApprovalStore(), events)
    subscription, _ = events.attach()

    await store.create_request(_approval(approval_id="appr-1"))

    delivered = [event async for event in subscription.drain()]
    assert [(event.scope, event.kind, dict(event.payload)) for event in delivered] == [
        (DeploymentScope.DECISION, DeploymentEventKind.DECISION_PROPOSED, {"proposal_id": "appr-1"})
    ]


async def test_deciding_a_request_publishes_decision_decided() -> None:
    events = DeploymentEventBroker()
    inner = _FakeApprovalStore()
    store = _EventPublishingApprovalStore(inner, events)
    await store.create_request(_approval(approval_id="appr-1"))
    subscription, _ = events.attach()

    await store.decide("appr-1", state=ApprovalState.APPROVED, decided_by="ada", decided_at=_NOW)

    delivered = [event async for event in subscription.drain()]
    assert [(event.scope, event.kind, dict(event.payload)) for event in delivered] == [
        (DeploymentScope.DECISION, DeploymentEventKind.DECISION_DECIDED, {"proposal_id": "appr-1"})
    ]


async def test_expiring_due_requests_publishes_one_expired_event_each() -> None:
    events = DeploymentEventBroker()
    inner = _FakeApprovalStore()
    store = _EventPublishingApprovalStore(inner, events)
    await store.create_request(_approval(approval_id="appr-1"))
    await store.create_request(_approval(approval_id="appr-2"))
    subscription, _ = events.attach()

    expired = await store.expire_due(_NOW + timedelta(hours=1))

    assert {row.approval_id for row in expired} == {"appr-1", "appr-2"}
    delivered = [event async for event in subscription.drain()]
    assert {(event.kind, dict(event.payload)["proposal_id"]) for event in delivered} == {
        (DeploymentEventKind.DECISION_EXPIRED, "appr-1"),
        (DeploymentEventKind.DECISION_EXPIRED, "appr-2"),
    }


# --- The one composition entry point ----------------------------------------


async def test_with_deployment_events_wraps_a_gateways_incidents_and_approvals() -> None:
    from platform.persistence.fakes import FakePersistence
    from platform.persistence.ports.transaction import TenantScope

    raw = FakePersistence()
    async with raw.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme")

    events = DeploymentEventBroker()
    wrapped = with_deployment_events(raw, events)
    subscription, _ = events.attach()

    scope = TenantScope(org_id="acme")
    async with wrapped.begin(scope) as uow:
        await uow.incidents.upsert(_incident(incident_id="inc-1", state=IncidentState.OPEN))

    delivered = [event async for event in subscription.drain()]
    assert [event.kind for event in delivered] == [DeploymentEventKind.INCIDENT_OPENED]
