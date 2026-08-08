"""The lifecycle: one incident per cause, one timeline, and one way to end.

Everything here is about *how many* incidents exist and *what they say happened*
— the two things a component that opens work on its own has to get right, and
the two an operator will notice immediately when it does not.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from platform.incidents import correlation
from platform.incidents.detection import DetectionIntake
from platform.incidents.errors import IncidentClosed, UnknownIncident
from platform.incidents.lifecycle import IncidentLifecycle, IncidentRaise
from platform.notifications.models import Severity
from platform.observation.detectors.model import (
    Condition,
    ConditionKind,
    DetectorDeclaration,
    GroupingKey,
)
from platform.observation.evaluation import DetectorFailure, EvaluationTick, TickOutcome
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import (
    IncidentOrigin,
    IncidentQuery,
    IncidentState,
    IncidentSubject,
    PersistenceGateway,
    Resource,
    Signal,
    SignalKind,
    TenantScope,
    TimelineKind,
)
from platform.persistence.ports.signal_store import signal_key

pytestmark = pytest.mark.unit

EPOCH = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def at(minutes: float = 0.0) -> datetime:
    """Return a fixed instant offset by ``minutes``."""
    return EPOCH + timedelta(minutes=minutes)


def sample(minutes: float, value: float, *, resource_id: str = "store-cove") -> Signal:
    """Return one numeric sample."""
    observed_at = at(minutes)
    return Signal(
        signal_id=signal_key("storage.used_percent", resource_id, observed_at),
        name="storage.used_percent",
        resource_id=resource_id,
        source="poller:proxmox",
        kind=SignalKind.NUMBER,
        observed_at=observed_at,
        value=value,
        interval_seconds=60,
    )


def datastore(resource_id: str, *, parent_id: str | None = None) -> Resource:
    """Return one datastore."""
    return Resource(
        resource_id=resource_id,
        kind="datastore",
        source="proxmox",
        native_id=resource_id,
        parent_id=parent_id,
    )


def near_full(grouping: GroupingKey = GroupingKey.DETECTOR) -> DetectorDeclaration:
    """Return the detector the tests fire."""
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
        grouping_key=grouping,
        team_node_id="team-payments",
    )


def a_raise(correlation_key: str = "detector:datastore-near-full") -> IncidentRaise:
    """Return a raise a test can hand to the lifecycle directly."""
    return IncidentRaise(
        correlation_key=correlation_key,
        title="Datastore near full",
        summary="store-cove is 95.65% full",
        origin=IncidentOrigin.DETECTOR,
        origin_id="datastore-near-full",
        severity="critical",
        subjects=(
            IncidentSubject(
                resource_id="store-cove",
                detail="store-cove is 95.65% full",
                evidence={"used_percent": "95.65"},
                observed_at=at(),
            ),
        ),
        cause="the datastore crossed ninety per cent and stayed there",
    )


@pytest.fixture
async def gateway() -> PersistenceGateway:
    """Return an in-memory gateway with one organisation."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme")
    return store


# --- The closed state set ------------------------------------------------------------


def test_the_state_set_is_closed_and_has_seven_members() -> None:
    """An eighth is a specification change, not a refactor."""
    assert len(tuple(IncidentState)) == 7
    assert {state for state in IncidentState if state.is_closed} == {
        IncidentState.RESOLVED,
        IncidentState.SUPPRESSED,
        IncidentState.CLOSED_WITHOUT_ACTION,
    }


async def test_no_transition_can_name_a_state_outside_the_set(
    gateway: PersistenceGateway,
) -> None:
    """The signature takes the enum, so an invented state is a type error and a value one."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        incident = await lifecycle.raise_incident(a_raise(), now=at())

        with pytest.raises(ValueError, match="not a valid IncidentState"):
            await lifecycle.transition(
                incident.incident_id,
                IncidentState("acknowledged-ish"),
                cause="somebody invented a state",
                now=at(1),
            )


# --- The timeline ----------------------------------------------------------------------


async def test_every_state_change_appears_with_its_cause_and_its_actor(
    gateway: PersistenceGateway,
) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        incident = await lifecycle.raise_incident(a_raise(), now=at())
        await lifecycle.transition(
            incident.incident_id,
            IncidentState.AWAITING_HUMAN,
            cause="the runbook needs a decision about deleting snapshots",
            actor="ada@example.test",
            now=at(5),
        )

        history = await lifecycle.timeline(incident.incident_id)

    assert [item.kind for item in history] == [TimelineKind.OPENED, TimelineKind.STATE_CHANGED]
    assert history[1].actor == "ada@example.test"
    assert "snapshots" in history[1].cause


async def test_a_state_change_without_a_cause_is_refused(
    gateway: PersistenceGateway,
) -> None:
    """A timeline of unexplained state changes reconstructs nothing."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        incident = await lifecycle.raise_incident(a_raise(), now=at())

        with pytest.raises(ValueError, match="needs a cause"):
            await lifecycle.transition(
                incident.incident_id, IncidentState.INVESTIGATING, cause="", now=at(1)
            )


async def test_an_operation_on_an_incident_nothing_raised_is_an_error(
    gateway: PersistenceGateway,
) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        with pytest.raises(UnknownIncident):
            await IncidentLifecycle(store=uow.incidents).transition(
                "i-nothing", IncidentState.INVESTIGATING, cause="x", now=at()
            )


async def test_a_closed_incident_cannot_be_moved(gateway: PersistenceGateway) -> None:
    """A recurrence is a new incident; writing it here would lose when it recurred."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        incident = await lifecycle.raise_incident(a_raise(), now=at())
        await lifecycle.close(
            incident.incident_id, reason="it was noise", actor="ada@example.test", now=at(1)
        )

        with pytest.raises(IncidentClosed):
            await lifecycle.transition(
                incident.incident_id, IncidentState.INVESTIGATING, cause="try again", now=at(2)
            )


# --- Opening exactly one ------------------------------------------------------------------


async def test_a_condition_crossing_and_holding_opens_exactly_one_incident(
    gateway: PersistenceGateway,
) -> None:
    """SC-001, first half."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.signals.append([sample(-5, 91.0), sample(-2, 92.0), sample(0, 93.0)])
        intake = DetectionIntake(
            lifecycle=IncidentLifecycle(store=uow.incidents),
            detectors={"datastore-near-full": near_full()},
        )
        outcome = await EvaluationTick(detectors=(near_full(),)).run(
            uow.signals, resources=(datastore("store-cove"),), now=at()
        )

        report = await intake.absorb(outcome, resources=(datastore("store-cove"),), now=at())
        all_incidents = await uow.incidents.query(IncidentQuery())

    assert len(report.opened) == 1
    assert len(all_incidents) == 1
    assert all_incidents[0].subject_ids == ("store-cove",)


async def test_a_condition_crossing_and_recovering_inside_the_duration_opens_none(
    gateway: PersistenceGateway,
) -> None:
    """SC-001, second half."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.signals.append([sample(-5, 50.0), sample(-3, 91.0), sample(0, 50.0)])
        intake = DetectionIntake(
            lifecycle=IncidentLifecycle(store=uow.incidents),
            detectors={"datastore-near-full": near_full()},
        )
        outcome = await EvaluationTick(detectors=(near_full(),)).run(
            uow.signals, resources=(datastore("store-cove"),), now=at()
        )

        await intake.absorb(outcome, resources=(datastore("store-cove"),), now=at())

        assert await uow.incidents.query(IncidentQuery()) == ()


async def test_the_same_condition_firing_again_correlates_rather_than_opening_a_second(
    gateway: PersistenceGateway,
) -> None:
    """SC-002."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        first = await lifecycle.raise_incident(a_raise(), now=at())
        second = await lifecycle.raise_incident(a_raise(), now=at(5))

        listed = await uow.incidents.query(IncidentQuery())
        history = await lifecycle.timeline(first.incident_id)

    assert first.incident_id == second.incident_id
    assert len(listed) == 1
    assert TimelineKind.CORRELATED in {item.kind for item in history}


async def test_one_cause_across_fifty_resources_is_one_incident_with_fifty_subjects(
    gateway: PersistenceGateway,
) -> None:
    """SC-005."""
    stores = tuple(f"store-{index:02d}" for index in range(50))
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.signals.append(
            [
                sample(minute, 95.0, resource_id=resource_id)
                for resource_id in stores
                for minute in (-5, -2, 0)
            ]
        )
        resources = tuple(datastore(resource_id) for resource_id in stores)
        intake = DetectionIntake(
            lifecycle=IncidentLifecycle(store=uow.incidents),
            detectors={"datastore-near-full": near_full()},
        )
        outcome = await EvaluationTick(detectors=(near_full(),)).run(
            uow.signals, resources=resources, now=at()
        )

        report = await intake.absorb(outcome, resources=resources, now=at())
        listed = await uow.incidents.query(IncidentQuery())

    assert len(listed) == 1
    assert len(report.opened) == 1
    assert listed[0].subject_ids == stores


async def test_a_detector_grouped_by_resource_opens_one_incident_each(
    gateway: PersistenceGateway,
) -> None:
    """The grouping is on the detector, where an operator can read it."""
    detector = near_full(GroupingKey.RESOURCE)
    stores = ("store-cove", "store-ridge")
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.signals.append(
            [
                sample(minute, 95.0, resource_id=resource_id)
                for resource_id in stores
                for minute in (-5, -2, 0)
            ]
        )
        resources = tuple(datastore(resource_id) for resource_id in stores)
        intake = DetectionIntake(
            lifecycle=IncidentLifecycle(store=uow.incidents),
            detectors={detector.detector_id: detector},
        )
        outcome = await EvaluationTick(detectors=(detector,)).run(
            uow.signals, resources=resources, now=at()
        )

        report = await intake.absorb(outcome, resources=resources, now=at())

    assert len(report.opened) == 2


def test_grouping_by_parent_puts_two_nodes_worth_of_datastores_apart() -> None:
    detector = near_full(GroupingKey.PARENT)

    one = correlation.for_detector(detector, datastore("store-cove", parent_id="node01"))
    two = correlation.for_detector(detector, datastore("store-ridge", parent_id="node02"))

    assert one != two


# --- Closing --------------------------------------------------------------------------------


async def test_a_recovered_condition_closes_its_incident_and_says_it_self_resolved(
    gateway: PersistenceGateway,
) -> None:
    """SC-003."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        intake = DetectionIntake(
            lifecycle=lifecycle, detectors={"datastore-near-full": near_full()}
        )
        await lifecycle.raise_incident(a_raise(), now=at())

        await uow.signals.append([sample(-5, 50.0), sample(-2, 51.0), sample(0, 52.0)])
        outcome = await EvaluationTick(detectors=(near_full(),)).run(
            uow.signals, resources=(datastore("store-cove"),), now=at()
        )
        report = await intake.absorb(outcome, resources=(datastore("store-cove"),), now=at())

    assert len(report.closed) == 1
    assert report.closed[0].state is IncidentState.RESOLVED
    assert report.closed[0].self_resolved
    assert report.closed[0].close_reason


async def test_an_incident_does_not_close_while_one_subject_is_still_firing(
    gateway: PersistenceGateway,
) -> None:
    """An incident about a node and twenty guests is not resolved because one recovered."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        intake = DetectionIntake(
            lifecycle=lifecycle, detectors={"datastore-near-full": near_full()}
        )
        resources = (datastore("store-cove"), datastore("store-ridge"))
        await uow.signals.append(
            [
                sample(minute, 95.0, resource_id=r.resource_id)
                for r in resources
                for minute in (-5, -2, 0)
            ]
        )
        first = await EvaluationTick(detectors=(near_full(),)).run(
            uow.signals, resources=resources, now=at()
        )
        await intake.absorb(first, resources=resources, now=at())

        # One recovers; the other does not.
        await uow.signals.append(
            [sample(minute, 50.0, resource_id="store-cove") for minute in (5, 8, 10)]
        )
        second = await EvaluationTick(detectors=(near_full(),)).run(
            uow.signals, resources=resources, now=at(10)
        )
        report = await intake.absorb(second, resources=resources, now=at(10))

        live = await uow.incidents.query(IncidentQuery(live_only=True))

    assert report.closed == ()
    assert len(live) == 1


async def test_a_human_may_close_an_incident_at_any_state_with_a_reason(
    gateway: PersistenceGateway,
) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        incident = await lifecycle.raise_incident(a_raise(), now=at())
        await lifecycle.transition(
            incident.incident_id,
            IncidentState.REMEDIATING,
            cause="a snapshot prune was approved",
            now=at(1),
        )

        closed = await lifecycle.close(
            incident.incident_id,
            reason="the datastore was expanded by hand",
            actor="ada@example.test",
            now=at(9),
        )

    assert closed.state is IncidentState.CLOSED_WITHOUT_ACTION
    assert closed.close_reason == "the datastore was expanded by hand"
    assert not closed.self_resolved


async def test_a_close_without_a_reason_is_refused(gateway: PersistenceGateway) -> None:
    """ "Closed by Ada" does not say whether it was fixed or dismissed."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        incident = await lifecycle.raise_incident(a_raise(), now=at())

        with pytest.raises(ValueError, match="needs a reason"):
            await lifecycle.close(
                incident.incident_id, reason="", actor="ada@example.test", now=at(1)
            )


# --- A subject that goes away -----------------------------------------------------------------


async def test_a_subject_going_absent_is_recorded_and_does_not_close_the_incident(
    gateway: PersistenceGateway,
) -> None:
    """Declared behaviour rather than accidental: a guest that vanished is evidence."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        lifecycle = IncidentLifecycle(store=uow.incidents)
        incident = await lifecycle.raise_incident(a_raise(), now=at())

        marked = await lifecycle.mark_subject_absent(incident.incident_id, "store-cove", now=at(5))
        history = await lifecycle.timeline(incident.incident_id)

    assert marked.state is IncidentState.OPEN
    assert marked.subjects[0].absent_since == at(5)
    assert TimelineKind.SUBJECT_ABSENT in {item.kind for item in history}


# --- A detector that could not run -----------------------------------------------------------


async def test_a_failing_detector_becomes_its_own_incident(
    gateway: PersistenceGateway,
) -> None:
    """SC-007, and in its own correlation namespace so it cannot merge with a real one."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        intake = DetectionIntake(
            lifecycle=IncidentLifecycle(store=uow.incidents),
            detectors={"datastore-near-full": near_full()},
        )
        outcome = TickOutcome(
            started_at=at(),
            finished_at=at(),
            failures=(
                DetectorFailure(
                    detector_id="datastore-near-full",
                    reason="RuntimeError: the store returned something unreadable",
                    failed_at=at(),
                    resource_id="store-cove",
                ),
            ),
        )

        report = await intake.absorb(outcome, now=at())

    assert len(report.failures) == 1
    assert report.failures[0].correlation_key.startswith("detector-failure:")
    assert "nothing is watching" in report.failures[0].summary
