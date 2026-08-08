"""The tick: what it concludes, what it survives, and what it refuses to hide.

Four properties, and each of them is the reason a piece of the design is shaped
the way it is.

A restart mid-tick does not double-fire, and two replicas reach one outcome,
because evaluation remembers nothing — not because either of them checked.

A detector replayed against stored signals reproduces exactly the firings that
happened, because the evaluator is pure.

And a detector that throws comes back as an attention item, because a monitoring
system that looks healthy by having stopped looking is the worst thing this
component could become.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from platform.notifications.models import Severity
from platform.observation.detectors.conditions import Verdict
from platform.observation.detectors.model import Condition, ConditionKind, DetectorDeclaration
from platform.observation.errors import ObservationBoundExceeded
from platform.observation.evaluation import EvaluationTick, evaluate_all, replay
from platform.observation.schedule import (
    TICK_JOB_ID,
    ObservationClaiming,
    interval_of,
    next_tick_after,
    tick_job,
)
from platform.observation.signals import SignalWindow, windows
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import (
    PersistenceGateway,
    Resource,
    Signal,
    SignalKind,
    TenantScope,
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


def datastore(resource_id: str = "store-cove") -> Resource:
    """Return one datastore in the estate."""
    return Resource(
        resource_id=resource_id, kind="datastore", source="proxmox", native_id=resource_id
    )


def near_full(detector_id: str = "datastore-near-full") -> DetectorDeclaration:
    """Return the detector every test in this file uses."""
    return DetectorDeclaration(
        detector_id=detector_id,
        name="Datastore near full",
        description="A datastore that fills stops every guest on it at once.",
        resource_kinds=("datastore",),
        signal="storage.used_percent",
        condition=Condition(kind=ConditionKind.THRESHOLD, fire_value=90.0, clear_value=80.0),
        for_seconds=300,
        recovery_seconds=300,
        severity=Severity.CRITICAL,
    )


@pytest.fixture
async def gateway() -> PersistenceGateway:
    """Return an in-memory gateway with one organisation."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme")
    return store


# --- The tick ---------------------------------------------------------------------


async def test_a_tick_evaluates_every_detector_over_every_subject_it_applies_to(
    gateway: PersistenceGateway,
) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.signals.append(
            [
                sample(-5, 91.0, resource_id="store-cove"),
                sample(-2, 92.0, resource_id="store-cove"),
                sample(0, 93.0, resource_id="store-cove"),
                sample(-5, 10.0, resource_id="store-ridge"),
                sample(0, 11.0, resource_id="store-ridge"),
            ]
        )

        outcome = await EvaluationTick(detectors=(near_full(),)).run(
            uow.signals,
            resources=(datastore("store-cove"), datastore("store-ridge")),
            now=at(),
        )

    assert outcome.subjects == 2
    assert [entry.resource_id for entry in outcome.findings] == ["store-cove"]
    assert len(outcome.evaluated) == 2


async def test_a_detector_does_not_evaluate_a_kind_it_does_not_apply_to(
    gateway: PersistenceGateway,
) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.signals.append(
            [sample(-5, 91.0, resource_id="node01"), sample(0, 93.0, resource_id="node01")]
        )

        node = Resource(resource_id="node01", kind="node", source="proxmox", native_id="node01")
        outcome = await EvaluationTick(detectors=(near_full(),)).run(
            uow.signals, resources=(node,), now=at()
        )

    assert outcome.evaluated == ()


async def test_a_detector_on_a_kind_no_resource_has_evaluates_nothing_and_does_not_fail(
    gateway: PersistenceGateway,
) -> None:
    """A detector waiting for an integration nobody has installed is not an error."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        outcome = await EvaluationTick(detectors=(near_full(),)).run(
            uow.signals, resources=(), now=at()
        )

    assert outcome.evaluated == ()
    assert outcome.failures == ()


# --- Restart, and two replicas -------------------------------------------------------


async def test_a_second_tick_over_the_same_signals_reaches_the_same_verdicts(
    gateway: PersistenceGateway,
) -> None:
    """A restart mid-tick cannot double-fire, because nothing was remembered."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.signals.append([sample(-5, 91.0), sample(-3, 92.0), sample(0, 93.0)])
        tick = EvaluationTick(detectors=(near_full(),))

        first = await tick.run(uow.signals, resources=(datastore(),), now=at())
        second = await tick.run(uow.signals, resources=(datastore(),), now=at())

    assert first.evaluated == second.evaluated
    assert [entry.verdict for entry in first.findings] == [Verdict.FIRING]


async def test_two_replicas_evaluating_the_same_instant_produce_one_outcome(
    gateway: PersistenceGateway,
) -> None:
    """Two ticks, two workers, one conclusion — and no coordination between them."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.signals.append([sample(-5, 91.0), sample(-2, 92.0), sample(0, 93.0)])

        replica_one = await EvaluationTick(detectors=(near_full(),)).run(
            uow.signals, resources=(datastore(),), now=at()
        )
        replica_two = await EvaluationTick(detectors=(near_full(),)).run(
            uow.signals, resources=(datastore(),), now=at()
        )

    assert replica_one.evaluated == replica_two.evaluated


async def test_only_one_worker_claims_the_tick(gateway: PersistenceGateway) -> None:
    """The scheduler's own lease, unchanged — there is no second mechanism here."""
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.schedules.upsert_job(tick_job(next_run_at=at(-1)))

    async with gateway.begin_system() as system:
        first = await ObservationClaiming.for_worker(system.jobs, "worker-a").claim(now=at())
        second = await ObservationClaiming.for_worker(system.jobs, "worker-b").claim(now=at())

    assert [claim.job_id for claim in first] == [TICK_JOB_ID]
    assert second == ()


def test_a_tick_interval_below_the_floor_is_refused() -> None:
    with pytest.raises(ObservationBoundExceeded, match="MIN_TICK_INTERVAL_SECONDS"):
        tick_job(next_run_at=at(), interval_seconds=1)


async def test_a_hand_edited_payload_costs_an_odd_tick_rather_than_no_ticks(
    gateway: PersistenceGateway,
) -> None:
    async with gateway.begin(TenantScope(org_id="acme")) as uow:
        await uow.schedules.upsert_job(tick_job(next_run_at=at(-1), interval_seconds=120))

    async with gateway.begin_system() as system:
        claims = await ObservationClaiming.for_worker(system.jobs, "worker-a").claim(now=at())

    assert interval_of(claims[0]) == 120
    assert next_tick_after(claims[0], now=at()) == at(2)


# --- Replay ---------------------------------------------------------------------------


def test_a_detector_replayed_against_history_reproduces_exactly_what_happened() -> None:
    """SC-009. A unit test rather than an integration one, because evaluation is pure."""
    # One sample a minute, so the window boundaries are the only thing the
    # assertion below is about.
    history = tuple(
        sample(minute, 50.0 if minute < -20 else 92.0 if minute < -5 else 70.0)
        for minute in range(-30, 1)
    )
    detectors = (near_full(),)
    kinds = {"store-cove": "datastore"}

    firings = [
        minute
        for minute in range(-30, 1)
        if any(
            entry.verdict is Verdict.FIRING
            for entry in replay(detectors, history, at=at(minute), kinds=kinds)
        )
    ]

    assert firings == list(range(-15, -5))
    # And again, from the same history: replay is a function of its inputs.
    assert firings == [
        minute
        for minute in range(-30, 1)
        if any(
            entry.verdict is Verdict.FIRING
            for entry in replay(detectors, history, at=at(minute), kinds=kinds)
        )
    ]


def test_replay_reads_no_clock_and_writes_nothing() -> None:
    """The property that makes the assertion above a test rather than a hope."""
    history = (sample(-5, 91.0), sample(0, 93.0))

    at_the_time = replay((near_full(),), history, at=at(), kinds={"store-cove": "datastore"})
    a_month_later = replay((near_full(),), history, at=at(), kinds={"store-cove": "datastore"})

    assert at_the_time == a_month_later


# --- A detector that throws --------------------------------------------------------------


def _exploding(window: SignalWindow) -> SignalWindow:
    """Return a window that raises the moment the evaluator reads it.

    Standing in for a defect inside a detector or the data it was handed. What
    the test is about is not this particular explosion but that *any* of them
    comes back as an attention item rather than as silence.
    """

    class Exploding(SignalWindow):
        @property
        def is_empty(self) -> bool:
            """Raise, the way a real defect would."""
            raise RuntimeError("the signal store returned something unreadable")

    return Exploding(
        name=window.name,
        resource_id=window.resource_id,
        opened_at=window.opened_at,
        closed_at=window.closed_at,
        samples=window.samples,
        last_seen=window.last_seen,
    )


def _window(resource_id: str, value: float) -> SignalWindow:
    """Return a window over two samples for ``resource_id``."""
    samples = (
        sample(-5, value, resource_id=resource_id),
        sample(0, value, resource_id=resource_id),
    )
    return windows(samples, opened_at=at(-10), closed_at=at(), latest=samples)[0]


def test_a_detector_that_throws_surfaces_as_an_attention_item() -> None:
    """Not skipped, not swallowed: a detector that stopped working is itself news."""
    broken = _exploding(_window("store-cove", 93.0))

    observations, failures = evaluate_all(
        (near_full("broken-detector"),),
        {broken.key: broken},
        kinds={"store-cove": "datastore"},
        now=at(),
    )

    assert observations == ()
    assert [entry.detector_id for entry in failures] == ["broken-detector"]
    assert "nothing is watching" in failures[0].summary


def test_one_unreadable_subject_does_not_stop_the_rest_of_the_estate() -> None:
    """A failure that took the tick down with it would be the outage it reports."""
    broken = _exploding(_window("store-cove", 93.0))
    fine = _window("store-ridge", 93.0)

    observations, failures = evaluate_all(
        (near_full(),),
        {broken.key: broken, fine.key: fine},
        kinds={"store-cove": "datastore", "store-ridge": "datastore"},
        now=at(),
    )

    assert [entry.resource_id for entry in observations] == ["store-ridge"]
    assert [entry.resource_id for entry in failures] == ["store-cove"]
