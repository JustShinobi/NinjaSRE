"""Detectors reading somebody else's history, and the two ways that can go wrong.

A detector that reads Prometheus can conclude something about a window during
which this deployment was not running. That is the whole reason the bridge earns
its place — and it is also why a metrics system that stops answering must never
be read as an estate with nothing wrong.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from config.constants.observability_bridge import (
    BRIDGE_SOURCE,
    MAX_HISTORY_LOOKBACK_SECONDS,
    PRECEDENCE_SOURCE_BRIDGE,
    PRECEDENCE_SOURCE_POLLING,
    PROXMOX_ESTATE_SOURCE,
)
from platform.estate.kinds import KIND_CONTAINER
from platform.notifications.models import Severity
from platform.observation.bridge.availability import (
    SourceOutage,
    failures_for_outage,
    raise_for_outage,
)
from platform.observation.bridge.errors import BridgeBoundExceeded, MetricsSourceUnreachable
from platform.observation.bridge.exporters import SHIPPED_RULES
from platform.observation.bridge.history import MetricsHistorySource
from platform.observation.bridge.mapping import EstateIndex
from platform.observation.bridge.ports import MetricPoint, MetricSeries
from platform.observation.bridge.precedence import PrecedenceRule, SignalPrecedence
from platform.observation.detectors.model import (
    Comparison,
    Condition,
    ConditionKind,
    DetectorDeclaration,
)
from platform.observation.evaluation import EvaluationTick
from platform.observation.sources.poller import Poller
from platform.observation.sources.port import (
    PollBudget,
    SignalDeclaration,
    SignalPage,
    SignalReader,
)
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import IncidentOrigin, Resource, SignalQuery, TenantScope

pytestmark = pytest.mark.unit

EPOCH = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
CLUSTER = "HAL9000"
SIGNAL = "guest.cpu.ratio"

CT100 = Resource(
    resource_id="res-ct100",
    kind=KIND_CONTAINER,
    source=PROXMOX_ESTATE_SOURCE,
    native_id=f"lxc/{CLUSTER}/1734000000/100",
    display_name="plex",
)
ESTATE = EstateIndex.of((CT100,))


@dataclass
class StubMetrics:
    """A metrics system holding one series' worth of history."""

    history_series: tuple[MetricSeries, ...] = ()
    fails: Exception | None = None
    windows: list[tuple[datetime, datetime, int]] = field(default_factory=list)

    async def series(self, *, matchers: tuple[str, ...], at: datetime) -> tuple[MetricSeries, ...]:
        """Return the same series a history read would return."""
        del matchers, at
        if self.fails is not None:
            raise self.fails
        return self.history_series

    async def history(
        self,
        *,
        matchers: tuple[str, ...],
        start: datetime,
        end: datetime,
        step_seconds: int,
    ) -> tuple[MetricSeries, ...]:
        """Record the window that was asked for and answer with the fixture."""
        del matchers
        self.windows.append((start, end, step_seconds))
        if self.fails is not None:
            raise self.fails
        return self.history_series


def busy_history(minutes: int = 12, value: float = 0.96) -> tuple[MetricSeries, ...]:
    """Return one series that has been over the threshold for ``minutes``."""
    return (
        MetricSeries(
            metric="pve_cpu_usage_ratio",
            labels={"id": "lxc/100"},
            samples=tuple(
                MetricPoint(observed_at=EPOCH - timedelta(minutes=minutes - offset), value=value)
                for offset in range(minutes + 1)
            ),
        ),
    )


def cpu_detector() -> DetectorDeclaration:
    """Return a detector that fires on sustained container CPU."""
    return DetectorDeclaration(
        detector_id="guest-cpu-saturated",
        name="Guest CPU saturated",
        description="a container pinned above 90% for ten minutes is not a spike",
        resource_kinds=(KIND_CONTAINER,),
        signal=SIGNAL,
        condition=Condition(
            kind=ConditionKind.THRESHOLD,
            comparison=Comparison.ABOVE,
            fire_value=0.9,
            clear_value=0.8,
        ),
        for_seconds=600,
        recovery_seconds=300,
        severity=Severity.HIGH,
    )


def history_source(metrics: StubMetrics) -> MetricsHistorySource:
    """Return the bridge-backed source for the fixture estate."""
    return MetricsHistorySource(
        metrics=metrics,
        signal_name=SIGNAL,
        matcher="pve_cpu_usage_ratio",
        rules=SHIPPED_RULES,
        estate=ESTATE,
    )


def test_the_history_source_satisfies_the_signal_reader_port() -> None:
    """A bridge-backed source is a source like any other, or the tick cannot use it."""
    assert isinstance(history_source(StubMetrics()), SignalReader)


@pytest.mark.asyncio
async def test_a_history_read_returns_every_sample_the_source_held() -> None:
    """T-011: history, not one instant. One sample per point, mapped to the resource."""
    metrics = StubMetrics(history_series=busy_history())

    page = await history_source(metrics).read(
        resource_ids=(CT100.resource_id,), at=EPOCH, budget=PollBudget()
    )

    assert isinstance(page, SignalPage)
    assert len(page.readings) == 13
    assert {reading.resource_id for reading in page.readings} == {CT100.resource_id}
    assert page.provider_calls == 1


@pytest.mark.asyncio
async def test_the_reading_says_where_it_came_from() -> None:
    """FR-023: a change in provenance is visible on the sample itself."""
    metrics = StubMetrics(history_series=busy_history())

    page = await history_source(metrics).read(resource_ids=(), at=EPOCH, budget=PollBudget())

    assert page.readings[0].labels["source"] == BRIDGE_SOURCE
    assert history_source(metrics).declaration.source == BRIDGE_SOURCE


@pytest.mark.asyncio
async def test_a_detector_fires_on_history_the_deployment_never_polled() -> None:
    """SC-003: the condition held for ten minutes and nothing here was running for it."""
    metrics = StubMetrics(history_series=busy_history())
    persistence = FakePersistence()
    async with persistence.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme")
    scope = TenantScope(org_id="acme")

    async with persistence.begin(scope) as uow:
        polled_before = await uow.signals.window(
            SignalQuery(names=(SIGNAL,), since=EPOCH - timedelta(hours=1), until=EPOCH)
        )
    assert polled_before == (), "the deployment's own polling never sampled this window"

    samples = await Poller(reader=history_source(metrics)).poll(
        resource_ids=(CT100.resource_id,), now=EPOCH
    )
    async with persistence.begin(scope) as uow:
        await uow.signals.append(samples)
        outcome = await EvaluationTick(detectors=(cpu_detector(),)).run(
            uow.signals, resources=(CT100,), now=EPOCH
        )

    assert [finding.detector_id for finding in outcome.findings] == ["guest-cpu-saturated"]


@pytest.mark.asyncio
async def test_an_unreachable_source_raises_rather_than_returning_an_empty_page() -> None:
    """FR-007: an empty page and a dead Prometheus produce opposite verdicts."""
    metrics = StubMetrics(fails=MetricsSourceUnreachable("prometheus", reason="refused"))

    with pytest.raises(MetricsSourceUnreachable):
        await Poller(reader=history_source(metrics)).poll(resource_ids=(), now=EPOCH)


def test_a_lookback_past_the_ceiling_is_refused_where_it_is_declared() -> None:
    """A query that can take the operator's own monitoring down is not configurable."""
    with pytest.raises(BridgeBoundExceeded):
        MetricsHistorySource(
            metrics=StubMetrics(),
            signal_name=SIGNAL,
            matcher="pve_cpu_usage_ratio",
            rules=SHIPPED_RULES,
            estate=ESTATE,
            lookback_seconds=MAX_HISTORY_LOOKBACK_SECONDS + 1,
        )


def test_dependent_detectors_report_inability_to_evaluate_not_absence_of_problems() -> None:
    """SC-008: the worst outcome is a detector that goes quiet and looks healthy."""
    outage = SourceOutage(
        source="prometheus", reason="connection refused", at=EPOCH, signals=(SIGNAL,)
    )
    other = DetectorDeclaration(
        detector_id="datastore-full",
        name="Datastore full",
        description="polled locally, unaffected by the bridge being down",
        resource_kinds=(),
        signal="datastore.used.ratio",
        condition=Condition(kind=ConditionKind.THRESHOLD, fire_value=0.9, clear_value=0.8),
        for_seconds=300,
        recovery_seconds=300,
    )

    failures = failures_for_outage((cpu_detector(), other), outage=outage)

    assert [failure.detector_id for failure in failures] == ["guest-cpu-saturated"]
    assert "connection refused" in failures[0].reason
    assert "nothing is watching" in failures[0].summary


def test_an_unavailable_source_is_itself_raised() -> None:
    """FR-007: the outage is an incident, not only a missing sample."""
    outage = SourceOutage(
        source="prometheus", reason="connection refused", at=EPOCH, signals=(SIGNAL,)
    )

    request = raise_for_outage(outage, team_node_id="acme")

    assert request.origin is IncidentOrigin.DETECTOR
    assert "prometheus" in request.title
    assert request.subjects
    assert request.correlation_key.startswith("bridge:")


def test_precedence_lets_exactly_one_source_produce_a_duplicated_signal() -> None:
    """SC-010: two detectors firing on one condition is two incidents about one problem."""
    precedence = SignalPrecedence(
        rules=(
            PrecedenceRule(
                signal=SIGNAL,
                winner=PRECEDENCE_SOURCE_BRIDGE,
                reason="prometheus has been scraping this for a year and we have not",
            ),
        )
    )

    assert precedence.produces(signal=SIGNAL, source=BRIDGE_SOURCE)
    assert not precedence.produces(signal=SIGNAL, source="proxmox")


def test_an_undeclared_duplicate_leaves_the_deployments_own_polling_in_charge() -> None:
    """FR-023: enabling a source must not silently change which detectors fire."""
    precedence = SignalPrecedence()

    assert precedence.produces(signal=SIGNAL, source="proxmox")
    assert not precedence.produces(signal=SIGNAL, source=BRIDGE_SOURCE)
    assert precedence.winner_for(SIGNAL) == PRECEDENCE_SOURCE_POLLING


def test_the_losing_source_stops_producing_rather_than_being_filtered() -> None:
    """A source that produced and was discarded would still spend the provider's quota."""
    precedence = SignalPrecedence(
        rules=(
            PrecedenceRule(
                signal=SIGNAL, winner=PRECEDENCE_SOURCE_BRIDGE, reason="the source has history"
            ),
        )
    )
    bridge = history_source(StubMetrics())
    polled = _PolledSource()

    kept, silenced = precedence.select((bridge, polled))

    assert [reader.declaration.source for reader in kept] == [BRIDGE_SOURCE]
    assert [entry.source for entry in silenced] == ["proxmox"]
    assert silenced[0].signal == SIGNAL
    assert silenced[0].reason


@dataclass
class _PolledSource:
    """The deployment's own poller for the same signal."""

    @property
    def declaration(self) -> SignalDeclaration:
        """Return a declaration naming the same signal the bridge covers."""
        return SignalDeclaration(source="proxmox", signals=(SIGNAL,))

    async def read(
        self, *, resource_ids: tuple[str, ...], at: datetime, budget: PollBudget
    ) -> SignalPage:
        """Return nothing; this source exists to be silenced."""
        del resource_ids, at, budget
        return SignalPage()
