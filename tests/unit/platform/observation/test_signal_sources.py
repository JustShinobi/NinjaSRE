"""Where signals come from, and the two facts a source must never confuse.

A source that stopped and a source that answered "nothing to report" produce
opposite verdicts from an absence detector, and only one of them is about the
estate. Everything in this file is ultimately about keeping those apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from platform.observation.errors import ObservationBoundExceeded
from platform.observation.signals import windows
from platform.observation.sources.estate_health import (
    ESTATE_HEALTH_SIGNAL,
    ESTATE_SOURCE,
    EstateHealthSource,
)
from platform.observation.sources.metrics import MetricSample, MetricsQuerySource
from platform.observation.sources.poller import Poller
from platform.observation.sources.port import (
    PollBudget,
    SignalDeclaration,
    SignalPage,
    SignalReader,
    SignalReading,
)
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import (
    HealthDerivation,
    Resource,
    ResourceHealth,
    SignalKind,
    TenantScope,
)

pytestmark = pytest.mark.unit

EPOCH = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def at(minutes: float = 0.0) -> datetime:
    """Return a fixed instant offset by ``minutes``."""
    return EPOCH + timedelta(minutes=minutes)


@dataclass
class StubReader:
    """A source that answers whatever a test tells it to."""

    readings: tuple[SignalReading, ...] = ()
    provider_calls: int = 1
    interval_seconds: int = 60
    rate_limit_per_minute: int = 60
    max_provider_calls: int = 2
    seen: list[tuple[str, ...]] = field(default_factory=list)
    fails: Exception | None = None

    @property
    def declaration(self) -> SignalDeclaration:
        """Return this stub's declaration."""
        return SignalDeclaration(
            source="stub",
            signals=("storage.used_percent",),
            interval_seconds=self.interval_seconds,
            rate_limit_per_minute=self.rate_limit_per_minute,
            max_provider_calls=self.max_provider_calls,
        )

    async def read(
        self, *, resource_ids: tuple[str, ...], at: datetime, budget: PollBudget
    ) -> SignalPage:
        """Return the configured page, or raise the configured failure."""
        del at, budget
        self.seen.append(resource_ids)
        if self.fails is not None:
            raise self.fails
        return SignalPage(readings=self.readings, provider_calls=self.provider_calls)


# --- The poller ------------------------------------------------------------------


def test_a_stub_reader_satisfies_the_source_protocol() -> None:
    assert isinstance(StubReader(), SignalReader)


async def test_a_poll_derives_an_identity_and_carries_the_declared_interval() -> None:
    """The interval travels on the sample, because a window has nothing else."""
    reader = StubReader(
        readings=(SignalReading(name="storage.used_percent", resource_id="store-cove", value=91.0),)
    )

    samples = await Poller(reader).poll(resource_ids=("store-cove",), now=at())

    assert len(samples) == 1
    assert samples[0].signal_id == f"storage.used_percent@store-cove@{at().isoformat()}"
    assert samples[0].interval_seconds == 60
    assert samples[0].source == "stub"


async def test_a_source_is_not_called_before_its_interval_has_passed() -> None:
    """Detection adds no provider calls beyond the ones a source asked for."""
    poller = Poller(StubReader(interval_seconds=300))

    assert poller.is_due(last_polled_at=None, now=at())
    assert not poller.is_due(last_polled_at=at(0), now=at(2))
    assert poller.is_due(last_polled_at=at(0), now=at(5))


async def test_a_source_that_overspends_its_declared_calls_is_reported() -> None:
    """Absorbed overspend is how a deployment finds its own detection in a vendor's dashboard."""
    reader = StubReader(provider_calls=9, max_provider_calls=2)

    with pytest.raises(ObservationBoundExceeded, match="provider calls per poll"):
        await Poller(reader).poll(resource_ids=("store-cove",), now=at())


async def test_a_failed_poll_raises_rather_than_returning_nothing() -> None:
    """An empty page and an unreachable provider are opposite facts."""
    reader = StubReader(fails=ConnectionError("the provider refused the connection"))

    with pytest.raises(ConnectionError):
        await Poller(reader).poll(resource_ids=("store-cove",), now=at())


def test_a_rate_limit_never_resolves_to_no_calls_at_all() -> None:
    """A limit that rounded down to zero would silently disable the source."""
    poller = Poller(StubReader(rate_limit_per_minute=1))

    assert poller.calls_allowed_per_tick(tick_seconds=15) == 1


def test_a_source_that_measures_nothing_is_refused_where_it_is_declared() -> None:
    with pytest.raises(ValueError, match="names no signals"):
        SignalDeclaration(source="stub", signals=())


def test_a_poll_interval_below_the_floor_is_refused() -> None:
    with pytest.raises(ObservationBoundExceeded, match="MIN_POLL_INTERVAL_SECONDS"):
        SignalDeclaration(source="stub", signals=("x",), interval_seconds=1)


# --- The estate's own health ------------------------------------------------------


async def test_the_estate_source_samples_every_resource_at_the_poll_instant() -> None:
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme")
    async with store.begin(TenantScope(org_id="acme")) as uow:
        await uow.estate.upsert(
            Resource(resource_id="node01", kind="node", source="proxmox", native_id="node01")
        )
        await uow.estate.record_health(
            "node01",
            HealthDerivation(state=ResourceHealth.UNHEALTHY, rule="provider", derived_at=at(-1)),
        )

        samples = await EstateHealthSource(uow.estate).read(now=at())

    assert [(entry.name, entry.state, entry.source) for entry in samples] == [
        (ESTATE_HEALTH_SIGNAL, ResourceHealth.UNHEALTHY.value, ESTATE_SOURCE)
    ]
    assert samples[0].kind is SignalKind.STATE


async def test_the_estate_source_back_fills_a_transition_at_the_instant_it_happened() -> None:
    """A state change between two polls is invisible unless the transition is read."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme")
    async with store.begin(TenantScope(org_id="acme")) as uow:
        await uow.estate.upsert(
            Resource(resource_id="node01", kind="node", source="proxmox", native_id="node01")
        )
        await uow.estate.record_health(
            "node01",
            HealthDerivation(state=ResourceHealth.HEALTHY, rule="provider", derived_at=at(-9)),
        )
        await uow.estate.record_health(
            "node01",
            HealthDerivation(state=ResourceHealth.UNHEALTHY, rule="provider", derived_at=at(-4)),
        )

        samples = await EstateHealthSource(uow.estate).read(now=at(), since=at(-5))

    assert sorted((entry.observed_at, entry.state) for entry in samples) == [
        (at(-4), ResourceHealth.UNHEALTHY.value),
        (at(), ResourceHealth.UNHEALTHY.value),
    ]


# --- A metrics query ---------------------------------------------------------------


@dataclass
class StubBackend:
    """A metrics system that returns whatever a test hands it."""

    samples: tuple[MetricSample, ...] = ()
    asked: list[str] = field(default_factory=list)

    async def evaluate(
        self, expression: str, *, resource_ids: tuple[str, ...], at: datetime
    ) -> tuple[MetricSample, ...]:
        """Return the configured samples and record the expression."""
        del resource_ids, at
        self.asked.append(expression)
        return self.samples


async def test_a_metrics_query_costs_one_call_however_many_resources_it_covers() -> None:
    backend = StubBackend(
        samples=(
            MetricSample(resource_id="ct-101", value=0.9),
            MetricSample(resource_id="ct-102", value=0.4),
        )
    )
    source = MetricsQuerySource(
        backend=backend, signal_name="cpu.saturation", expression="rate(cpu[5m])"
    )

    page = await source.read(
        resource_ids=("ct-101", "ct-102"),
        at=at(),
        budget=PollBudget.for_declaration(source.declaration),
    )

    assert page.provider_calls == 1
    assert [reading.resource_id for reading in page.readings] == ["ct-101", "ct-102"]
    assert backend.asked == ["rate(cpu[5m])"]


async def test_a_resource_the_query_has_no_data_for_is_absent_rather_than_nought() -> None:
    """A nought that meant "no data" would fire every below-threshold detector."""
    backend = StubBackend(samples=(MetricSample(resource_id="ct-101", value=0.9),))
    source = MetricsQuerySource(
        backend=backend, signal_name="cpu.saturation", expression="rate(cpu[5m])"
    )

    page = await source.read(
        resource_ids=("ct-101", "ct-102"),
        at=at(),
        budget=PollBudget.for_declaration(source.declaration),
    )

    assert [reading.resource_id for reading in page.readings] == ["ct-101"]


# --- Silence, from the window's point of view --------------------------------------


async def test_a_series_that_stopped_is_distinguishable_from_one_reporting_healthily() -> None:
    """The whole point of ``latest``: an empty window is not an answer on its own."""
    reader = StubReader(
        readings=(SignalReading(name="storage.used_percent", resource_id="store-cove", value=10.0),)
    )
    stale = await Poller(reader).poll(resource_ids=("store-cove",), now=at(-60))
    fresh = await Poller(reader).poll(resource_ids=("store-cove",), now=at(-1))

    quiet, healthy = (
        windows(
            (),
            opened_at=at(-5),
            closed_at=at(),
            latest=(stale[0],),
        ),
        windows((fresh[0],), opened_at=at(-5), closed_at=at(), latest=(fresh[0],)),
    )

    assert quiet[0].is_empty
    assert quiet[0].is_silent(at())
    assert not healthy[0].is_silent(at())


async def test_a_series_nobody_has_ever_measured_is_not_a_series_that_stopped() -> None:
    empty = windows((), opened_at=at(-5), closed_at=at())

    assert empty == ()
