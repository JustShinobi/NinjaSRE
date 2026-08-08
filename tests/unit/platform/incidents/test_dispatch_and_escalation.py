"""Dispatch and escalation: how much work an incident may start, and who gets told.

The two properties this file is about are the ones a component that starts work
on its own has to have before it is switched on, not after the first storm.

A hundred simultaneous incidents must not become a hundred simultaneous runs,
and an escalation must stop the moment somebody deals with the incident. The
second one is not politeness: an escalation that fires after an incident closed
teaches people to filter escalations, and the next real one is filtered too.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from config.constants.observation import (
    MAX_DISPATCHES_PER_HOUR,
    MAX_DISPATCHES_PER_TEAM_PER_HOUR,
)
from platform.incidents.dispatch import (
    DispatchLimits,
    IncidentDispatcher,
    RunStarter,
    objective_for,
)
from platform.incidents.escalation import IncidentEscalation
from platform.incidents.lifecycle import IncidentLifecycle, IncidentRaise
from platform.notifications.escalation import EscalationRegistry, EscalationState
from platform.notifications.models import Audience, NotificationSink, SinkKind
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import (
    Incident,
    IncidentOrigin,
    IncidentState,
    IncidentSubject,
    PersistenceGateway,
    TenantScope,
    TimelineKind,
)

pytestmark = pytest.mark.unit

EPOCH = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)

SINK = NotificationSink(
    kind=SinkKind.WEBHOOK, target="https://example.test/hook", audience=Audience.PRIVATE
)


def at(minutes: float = 0.0) -> datetime:
    """Return a fixed instant offset by ``minutes``."""
    return EPOCH + timedelta(minutes=minutes)


@dataclass
class RecordingStarter:
    """A run starter that records what it was asked and hands back an identifier."""

    started: list[tuple[str, str]] = field(default_factory=list)

    async def start(self, *, incident: Incident, objective: str) -> str:
        """Record the request and return a run id derived from the incident."""
        self.started.append((incident.incident_id, objective))
        return f"run-{len(self.started):03d}"


def a_raise(
    key: str = "detector:datastore-near-full",
    *,
    team: str = "team-payments",
    severity: str = "critical",
    subjects: tuple[str, ...] = ("store-cove",),
) -> IncidentRaise:
    """Return one raise."""
    return IncidentRaise(
        correlation_key=key,
        title="Datastore near full",
        summary="store-cove is 95.65% full",
        origin=IncidentOrigin.DETECTOR,
        origin_id="datastore-near-full",
        severity=severity,
        subjects=tuple(
            IncidentSubject(
                resource_id=resource_id,
                detail=f"{resource_id} is 95.65% full",
                evidence={"used_percent": "95.65"},
                observed_at=at(),
            )
            for resource_id in subjects
        ),
        team_node_id=team,
        cause="the datastore crossed ninety per cent and stayed there",
    )


@pytest.fixture
async def gateway() -> PersistenceGateway:
    """Return an in-memory gateway with one organisation."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme")
    return store


def test_a_starter_that_records_satisfies_the_protocol() -> None:
    assert isinstance(RecordingStarter(), RunStarter)


# --- The objective ------------------------------------------------------------------


async def test_the_objective_names_the_incident_its_subjects_and_the_evidence(
    gateway: PersistenceGateway,
) -> None:
    """Derived, so nobody has to restate what the incident already says."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        incident = await IncidentLifecycle(store=uow.incidents).raise_incident(a_raise(), now=at())

    objective = objective_for(incident)

    assert "Datastore near full" in objective
    assert "store-cove" in objective
    assert "used_percent=95.65" in objective


async def test_the_objective_counts_the_subjects_it_does_not_name(
    gateway: PersistenceGateway,
) -> None:
    """A prompt made of five hundred identifiers is one the model reads past."""
    stores = tuple(f"store-{index:02d}" for index in range(50))
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        incident = await IncidentLifecycle(store=uow.incidents).raise_incident(
            a_raise(subjects=stores), now=at()
        )

    assert "and 42 other(s)" in objective_for(incident)


async def test_a_run_started_from_an_incident_links_back_to_it(
    gateway: PersistenceGateway,
) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        incident = await lifecycle.raise_incident(a_raise(), now=at())
        dispatcher = IncidentDispatcher(lifecycle=lifecycle, starter=RecordingStarter())

        decision = await dispatcher.dispatch(incident, now=at())
        linked = await uow.incidents.get(incident.incident_id)
        history = await lifecycle.timeline(incident.incident_id)

    assert decision.allowed
    assert linked is not None
    assert linked.run_ids == (decision.run_id,)
    assert linked.state is IncidentState.INVESTIGATING
    assert TimelineKind.RUN_STARTED in {item.kind for item in history}


# --- One run per correlation -------------------------------------------------------------


async def test_a_second_firing_does_not_start_a_second_run(
    gateway: PersistenceGateway,
) -> None:
    """The second run would investigate the same thing and report it twice."""
    starter = RecordingStarter()
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        dispatcher = IncidentDispatcher(lifecycle=lifecycle, starter=starter)

        first = await lifecycle.raise_incident(a_raise(), now=at())
        await dispatcher.dispatch(first, now=at())

        # The same condition fires again and correlates onto the same incident.
        again = await lifecycle.raise_incident(a_raise(), now=at(5))
        second = await dispatcher.dispatch(again, now=at(5))

    assert len(starter.started) == 1
    assert second.held
    # And the refusal names the run that is already investigating it, so a
    # caller can point at it rather than wondering what happened.
    assert second.run_id == "run-001"


async def test_a_closed_incident_starts_nothing(gateway: PersistenceGateway) -> None:
    starter = RecordingStarter()
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        incident = await lifecycle.raise_incident(a_raise(), now=at())
        closed = await lifecycle.close(
            incident.incident_id, reason="it was noise", actor="ada@example.test", now=at(1)
        )

        decision = await IncidentDispatcher(lifecycle=lifecycle, starter=starter).dispatch(
            closed, now=at(2)
        )

    assert decision.held
    assert starter.started == []


# --- The rate limits ------------------------------------------------------------------------


async def test_a_hundred_simultaneous_incidents_do_not_start_a_hundred_runs(
    gateway: PersistenceGateway,
) -> None:
    """The case correlation cannot see: a hundred unrelated things at once."""
    starter = RecordingStarter()
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        dispatcher = IncidentDispatcher(lifecycle=lifecycle, starter=starter)

        incidents = tuple(
            [
                await lifecycle.raise_incident(
                    a_raise(f"detector:d-{index:03d}", subjects=(f"store-{index:03d}",)),
                    now=at(),
                )
                for index in range(100)
            ]
        )
        decisions = await dispatcher.dispatch_all(incidents, now=at())

    assert len(starter.started) == MAX_DISPATCHES_PER_TEAM_PER_HOUR
    assert sum(1 for decision in decisions if decision.allowed) == (
        MAX_DISPATCHES_PER_TEAM_PER_HOUR
    )
    assert all(decision.reason for decision in decisions if decision.held)


async def test_the_per_team_limit_is_per_team(gateway: PersistenceGateway) -> None:
    limits = DispatchLimits(per_team=2, overall=MAX_DISPATCHES_PER_HOUR)

    assert limits.check("team-payments", at=at()) == ""
    limits.record("team-payments", at=at())
    limits.record("team-payments", at=at())

    assert limits.check("team-payments", at=at()) != ""
    assert limits.check("team-search", at=at()) == ""


async def test_the_global_limit_binds_across_teams() -> None:
    """Fifty teams each under their own limit is still an unbounded deployment."""
    limits = DispatchLimits(per_team=10, overall=3)

    for index in range(3):
        limits.record(f"team-{index}", at=at())

    assert limits.check("team-fresh", at=at()) != ""


async def test_the_window_slides(gateway: PersistenceGateway) -> None:
    limits = DispatchLimits(per_team=1, overall=10, window_seconds=3_600.0)
    limits.record("team-payments", at=at(-120))

    assert limits.check("team-payments", at=at()) == ""


async def test_a_held_dispatch_is_recorded_on_the_incident(
    gateway: PersistenceGateway,
) -> None:
    """An incident sitting at open with no explanation is not an answer."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        dispatcher = IncidentDispatcher(
            lifecycle=lifecycle,
            starter=RecordingStarter(),
            limits=DispatchLimits(per_team=0, overall=10),
        )
        incident = await lifecycle.raise_incident(a_raise(), now=at())

        decision = await dispatcher.dispatch(incident, now=at())
        stored = await uow.incidents.get(incident.incident_id)
        history = await lifecycle.timeline(incident.incident_id)

    assert decision.held
    assert stored is not None
    assert any("dispatch held" in action for action in stored.actions)
    assert TimelineKind.ACTION_TAKEN in {item.kind for item in history}
    assert dispatcher.limits.held["team-payments"] == 1


async def test_the_most_urgent_incidents_get_the_budget(
    gateway: PersistenceGateway,
) -> None:
    """Not everything gets a run, so the ones that do should be the ones that matter."""
    starter = RecordingStarter()
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        dispatcher = IncidentDispatcher(
            lifecycle=lifecycle, starter=starter, limits=DispatchLimits(per_team=1, overall=10)
        )
        low = await lifecycle.raise_incident(
            a_raise("detector:low", severity="low", subjects=("store-low",)), now=at(-60)
        )
        critical = await lifecycle.raise_incident(
            a_raise("detector:critical", severity="critical", subjects=("store-crit",)), now=at()
        )

        await dispatcher.dispatch_all((low, critical), now=at())

    assert [entry[0] for entry in starter.started] == [critical.incident_id]


# --- Escalation ---------------------------------------------------------------------------------


async def test_an_incident_nobody_addressed_escalates(gateway: PersistenceGateway) -> None:
    registry = EscalationRegistry(delay_seconds=300.0)
    escalation = IncidentEscalation(registry=registry, default_sink=SINK)

    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        incident = await IncidentLifecycle(store=uow.incidents).raise_incident(a_raise(), now=at())

    escalation.schedule(incident, at=at())

    assert escalation.due(at=at(4)) == ()
    fired = escalation.due(at=at(6))
    assert [item.item_id for item in fired] == [incident.incident_id]
    assert fired[0].state is EscalationState.FIRED


async def test_escalation_stops_when_the_incident_closes(
    gateway: PersistenceGateway,
) -> None:
    """An escalation that fired after somebody closed it trains people to ignore them."""
    registry = EscalationRegistry(delay_seconds=300.0)
    escalation = IncidentEscalation(registry=registry, default_sink=SINK)

    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        incident = await lifecycle.raise_incident(a_raise(), now=at())
        escalation.schedule(incident, at=at())

        closed = await lifecycle.close(
            incident.incident_id,
            reason="the datastore was expanded by hand",
            actor="ada@example.test",
            now=at(2),
        )
        cancelled = escalation.cancel(closed)

    assert cancelled is not None
    assert escalation.due(at=at(60)) == ()
    assert [item.item_id for item in registry.cancelled] == [incident.incident_id]


async def test_a_suppressed_incident_escalates_to_nobody(
    gateway: PersistenceGateway,
) -> None:
    registry = EscalationRegistry(delay_seconds=300.0)
    escalation = IncidentEscalation(registry=registry, default_sink=SINK)

    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        incident = await lifecycle.raise_incident(a_raise(), now=at())
        suppressed = await lifecycle.suppress(
            incident.incident_id,
            by="maintenance-window",
            reason="swapping the disk shelf",
            now=at(1),
        )

    assert escalation.schedule(suppressed, at=at(1)) is None
    assert escalation.due(at=at(60)) == ()


async def test_a_firing_leaves_a_line_on_the_incidents_own_timeline(
    gateway: PersistenceGateway,
) -> None:
    """ "Nobody was told" and "three people were told" are different facts."""
    registry = EscalationRegistry(delay_seconds=300.0)
    escalation = IncidentEscalation(registry=registry, default_sink=SINK)

    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        incident = await lifecycle.raise_incident(a_raise(), now=at())
        escalation.schedule(incident, at=at())

        fired = escalation.due(at=at(6))
        await uow.incidents.append(escalation.timeline_entries(fired, at=at(6)))
        history = await lifecycle.timeline(incident.incident_id)

    assert [item.kind for item in history][-1] is TimelineKind.ESCALATED
    assert history[-1].cause
