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
    _PendingEvents,
    with_deployment_events,
)
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports.approval_store import ApprovalRequest, ApprovalState
from platform.persistence.ports.incident_store import (
    Incident,
    IncidentOrigin,
    IncidentState,
    IncidentSubject,
)
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope
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
    """The four write methods the decorator calls, backed by a dict."""

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

    async def discard(
        self,
        approval_id: str,
        *,
        discarded_by: str,
        discarded_at: datetime,
    ) -> ApprovalRequest:
        from dataclasses import replace

        current = self._rows[approval_id]
        discarded = replace(
            current,
            state=ApprovalState.DISCARDED,
            decided_by=discarded_by,
            decided_at=discarded_at,
        )
        self._rows[approval_id] = discarded
        return discarded

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
#
# A store wrapper queues; only a committed unit of work publishes. These tests
# hold the two halves apart deliberately — `flush` stands in for the commit the
# gateway performs — so what each write *earns* is under test separately from
# when the channel hears about it.


async def test_a_brand_new_incident_publishes_opened() -> None:
    events = DeploymentEventBroker()
    pending = _PendingEvents(org_id="acme")
    store = _EventPublishingIncidentStore(_FakeIncidentStore(), pending)
    subscription, _ = events.attach(org_id="acme")

    await store.upsert(_incident(incident_id="inc-1", state=IncidentState.OPEN))
    await pending.flush(events)

    delivered = [event async for event in subscription.drain()]
    assert [(event.scope, event.kind, dict(event.payload)) for event in delivered] == [
        (DeploymentScope.INCIDENT, DeploymentEventKind.INCIDENT_OPENED, {"incident_id": "inc-1"})
    ]


async def test_closing_a_live_incident_publishes_closed() -> None:
    events = DeploymentEventBroker()
    pending = _PendingEvents(org_id="acme")
    inner = _FakeIncidentStore()
    store = _EventPublishingIncidentStore(inner, pending)
    await store.upsert(_incident(incident_id="inc-1", state=IncidentState.OPEN))
    # The unit that opened the incident committed before this one began.
    await pending.flush(events)
    subscription, _ = events.attach(org_id="acme")

    await store.upsert(_incident(incident_id="inc-1", state=IncidentState.RESOLVED, closed_at=_NOW))
    await pending.flush(events)

    delivered = [event async for event in subscription.drain()]
    assert [(event.scope, event.kind, dict(event.payload)) for event in delivered] == [
        (DeploymentScope.INCIDENT, DeploymentEventKind.INCIDENT_CLOSED, {"incident_id": "inc-1"})
    ]


async def test_a_transition_between_two_live_states_publishes_nothing() -> None:
    events = DeploymentEventBroker()
    pending = _PendingEvents(org_id="acme")
    inner = _FakeIncidentStore()
    store = _EventPublishingIncidentStore(inner, pending)
    await store.upsert(_incident(incident_id="inc-1", state=IncidentState.OPEN))
    await pending.flush(events)
    subscription, _ = events.attach(org_id="acme")

    # A state change that is not a close — the fake models this as writing
    # OPEN again, which is the same live-to-live case a triage transition is.
    await store.upsert(_incident(incident_id="inc-1", state=IncidentState.OPEN))
    await pending.flush(events)

    delivered = [event async for event in subscription.drain()]
    assert delivered == []


async def test_reads_pass_through_the_decorator_untouched() -> None:
    pending = _PendingEvents(org_id="acme")
    inner = _FakeIncidentStore()
    store = _EventPublishingIncidentStore(inner, pending)
    written = await store.upsert(_incident(incident_id="inc-1", state=IncidentState.OPEN))

    found = await store.get("inc-1")
    assert found == written


# --- Decisions --------------------------------------------------------------


async def test_creating_a_request_publishes_decision_proposed() -> None:
    events = DeploymentEventBroker()
    pending = _PendingEvents(org_id="acme")
    store = _EventPublishingApprovalStore(_FakeApprovalStore(), pending)
    subscription, _ = events.attach(org_id="acme")

    await store.create_request(_approval(approval_id="appr-1"))
    await pending.flush(events)

    delivered = [event async for event in subscription.drain()]
    assert [(event.scope, event.kind, dict(event.payload)) for event in delivered] == [
        (DeploymentScope.DECISION, DeploymentEventKind.DECISION_PROPOSED, {"proposal_id": "appr-1"})
    ]


async def test_deciding_a_request_publishes_decision_decided() -> None:
    events = DeploymentEventBroker()
    pending = _PendingEvents(org_id="acme")
    inner = _FakeApprovalStore()
    store = _EventPublishingApprovalStore(inner, pending)
    await store.create_request(_approval(approval_id="appr-1"))
    await pending.flush(events)
    subscription, _ = events.attach(org_id="acme")

    await store.decide("appr-1", state=ApprovalState.APPROVED, decided_by="ada", decided_at=_NOW)
    await pending.flush(events)

    delivered = [event async for event in subscription.drain()]
    assert [(event.scope, event.kind, dict(event.payload)) for event in delivered] == [
        (DeploymentScope.DECISION, DeploymentEventKind.DECISION_DECIDED, {"proposal_id": "appr-1"})
    ]


async def test_discarding_a_request_publishes_decision_discarded() -> None:
    """Discarding is a write path of its own — `/v1/proposals/{id}/discard`
    moves a pending or expired row to DISCARDED without going anywhere near
    `decide`. Publishing nothing for it left every client but the one that
    performed it counting a row that was gone, indefinitely: the console stops
    polling while this stream is connected, so the correction never arrives."""
    events = DeploymentEventBroker()
    pending = _PendingEvents(org_id="acme")
    inner = _FakeApprovalStore()
    store = _EventPublishingApprovalStore(inner, pending)
    await store.create_request(_approval(approval_id="appr-1"))
    await pending.flush(events)
    subscription, _ = events.attach(org_id="acme")

    await store.discard("appr-1", discarded_by="ada", discarded_at=_NOW)
    await pending.flush(events)

    delivered = [event async for event in subscription.drain()]
    assert [(event.scope, dict(event.payload)) for event in delivered] == [
        (DeploymentScope.DECISION, {"proposal_id": "appr-1"})
    ]
    assert delivered[0].kind is DeploymentEventKind.DECISION_DISCARDED


async def test_expiring_due_requests_publishes_one_expired_event_each() -> None:
    events = DeploymentEventBroker()
    pending = _PendingEvents(org_id="acme")
    inner = _FakeApprovalStore()
    store = _EventPublishingApprovalStore(inner, pending)
    await store.create_request(_approval(approval_id="appr-1"))
    await store.create_request(_approval(approval_id="appr-2"))
    await pending.flush(events)
    subscription, _ = events.attach(org_id="acme")

    expired = await store.expire_due(_NOW + timedelta(hours=1))
    await pending.flush(events)

    assert {row.approval_id for row in expired} == {"appr-1", "appr-2"}
    delivered = [event async for event in subscription.drain()]
    assert {(event.kind, dict(event.payload)["proposal_id"]) for event in delivered} == {
        (DeploymentEventKind.DECISION_EXPIRED, "appr-1"),
        (DeploymentEventKind.DECISION_EXPIRED, "appr-2"),
    }


# --- The one composition entry point ----------------------------------------


async def test_with_deployment_events_wraps_a_gateways_incidents_and_approvals() -> None:
    events = DeploymentEventBroker()
    wrapped = await _tapped_gateway_for("acme", events)
    subscription, _ = events.attach(org_id="acme")

    scope = TenantScope(org_id="acme")
    async with wrapped.begin(scope) as uow:
        await uow.incidents.upsert(_incident(incident_id="inc-1", state=IncidentState.OPEN))

    delivered = [event async for event in subscription.drain()]
    assert [event.kind for event in delivered] == [DeploymentEventKind.INCIDENT_OPENED]


# --- The transaction boundary -----------------------------------------------


async def _tapped_gateway_for(org_id: str, events: DeploymentEventBroker) -> PersistenceGateway:
    """Return a tapped gateway over an in-memory store that knows ``org_id``."""
    raw = FakePersistence()
    async with raw.begin_system() as system:
        await system.orgs.create_organisation(org_id, org_id.title())
    return with_deployment_events(raw, events)


async def test_a_unit_that_raises_after_the_write_publishes_nothing() -> None:
    """An event announces a fact the database holds. A unit that rolled back
    holds none of them.

    The pair that makes this concrete is `platform/approvals/service.py`:
    `create_request` and `store_rollback_plan` run in one unit, and a failure
    in the second undoes the first. Announcing the proposal from inside the
    unit would put a decision on the wire that no reader can then find.
    """
    events = DeploymentEventBroker()
    gateway = await _tapped_gateway_for("acme", events)
    subscription, _ = events.attach(org_id="acme")

    with pytest.raises(RuntimeError):
        async with gateway.begin(TenantScope(org_id="acme")) as uow:
            await uow.approvals.create_request(_approval(approval_id="appr-1"))
            raise RuntimeError("the second write in the same unit failed")

    delivered = [event async for event in subscription.drain()]
    assert delivered == []


async def test_a_committed_unit_publishes_everything_it_wrote_in_order() -> None:
    """Held until the block ends, then released in the order they were earned."""
    events = DeploymentEventBroker()
    gateway = await _tapped_gateway_for("acme", events)
    subscription, _ = events.attach(org_id="acme")

    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.incidents.upsert(_incident(incident_id="inc-1", state=IncidentState.OPEN))
        await uow.approvals.create_request(_approval(approval_id="appr-1"))
        during = [event async for event in subscription.drain()]
        assert during == [], "nothing is announced while the unit is still open"

    delivered = [event async for event in subscription.drain()]
    assert [event.kind for event in delivered] == [
        DeploymentEventKind.INCIDENT_OPENED,
        DeploymentEventKind.DECISION_PROPOSED,
    ]


async def test_a_rollback_only_unit_publishes_nothing() -> None:
    """`mark_rollback_only` abandons the writes without raising, so the block
    ends normally — and the events it earned have to be dropped anyway."""
    events = DeploymentEventBroker()
    gateway = await _tapped_gateway_for("acme", events)
    subscription, _ = events.attach(org_id="acme")

    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.incidents.upsert(_incident(incident_id="inc-1", state=IncidentState.OPEN))
        uow.mark_rollback_only()

    delivered = [event async for event in subscription.drain()]
    assert delivered == []


# --- Tenancy ------------------------------------------------------------------


async def test_each_organisation_hears_only_its_own_writes() -> None:
    """One gateway, one broker, two organisations — the shape a deployment
    actually has, modelled on the two-scope setup
    `tests/contract/persistence/test_atomicity.py` uses to prove one tenant's
    rollback leaves another's work alone.

    The stamp comes from the scope the unit of work was opened for, so a write
    cannot be attributed to a tenant other than the one whose transaction
    performed it.
    """
    events = DeploymentEventBroker()
    raw = FakePersistence()
    async with raw.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme")
        await system.orgs.create_organisation("initech", "Initech")
    gateway = with_deployment_events(raw, events)

    acme, _ = events.attach(org_id="acme")
    initech, _ = events.attach(org_id="initech")

    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.incidents.upsert(_incident(incident_id="acme-inc", state=IncidentState.OPEN))
    async with gateway.begin(TenantScope(org_id="initech")) as uow:
        await uow.approvals.create_request(_approval(approval_id="initech-appr"))

    assert [dict(event.payload) async for event in acme.drain()] == [{"incident_id": "acme-inc"}]
    assert [dict(event.payload) async for event in initech.drain()] == [
        {"proposal_id": "initech-appr"}
    ]
