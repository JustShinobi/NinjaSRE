"""A signal source backed by somebody else's history rather than by our own polling.

This is the module that makes the bridge worth having. The deployment's own
poller can only ever know what it sampled while it was running; a metrics system
the operator has been running for a year knows what happened last Tuesday at
three in the morning. A detector reading through this source can conclude that a
condition has held for ten minutes on a deployment that started ninety seconds
ago — which no amount of local polling can recover.

**It is a ``SignalReader`` like any other.** The tick, the poller, the budget
and the retention sweep all work unchanged. What differs is where the samples
come from and what the reading says about that: every reading carries the source
it came from, so a change in provenance is visible on the sample rather than
inferable from configuration.

**Nothing is copied.** One read produces the samples a detector's window needs
and no more. The series stay in the metrics system, which is where the
operator's retention decision lives; what lands here is what a detector is about
to evaluate, under the same retention as every other signal.

**A failed read raises.** It has to. An empty page and an unreachable Prometheus
produce opposite verdicts from a threshold detector, and only one of them is
about the estate.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from config.constants.observability_bridge import (
    BRIDGE_SOURCE,
    DEFAULT_HISTORY_LOOKBACK_SECONDS,
    DEFAULT_HISTORY_STEP_SECONDS,
    MAX_HISTORY_LOOKBACK_SECONDS,
    MAX_HISTORY_SAMPLES,
)
from platform.observation.bridge.errors import BridgeBoundExceeded
from platform.observation.bridge.mapping import (
    EstateIndex,
    LabelRule,
    MappedSeries,
    SeriesMapping,
    map_series,
)
from platform.observation.bridge.ports import MetricsSource
from platform.observation.sources.port import (
    PollBudget,
    SignalDeclaration,
    SignalPage,
    SignalReading,
)
from platform.persistence.ports.signal_store import SignalKind

#: What a reading's labels call the provenance of the sample. On the reading
#: rather than only on the declaration, because a window holds samples and a
#: caller asking "where did this number come from" has the sample in its hand.
PROVENANCE_LABEL = "source"

#: What a reading's labels call whose account of the resource it is — the
#: hypervisor's, the machine's, or the guest's own.
VIEW_LABEL = "view"


@dataclass(frozen=True, slots=True)
class MetricsHistorySource:
    """One signal, read from a metrics system's history and mapped to the estate.

    The mapping rules and the estate index are held rather than looked up per
    read, because the join is rebuilt on its own schedule and rebuilding it
    inside a poll would multiply its cost by the number of sources.
    """

    metrics: MetricsSource
    #: What the resulting signal is called. Named rather than derived from the
    #: matcher, because an operator reads the name and nobody wants a signal
    #: called ``pve_cpu_usage_ratio{id=~"lxc/.*"}``.
    signal_name: str
    matcher: str
    rules: Sequence[LabelRule]
    estate: EstateIndex
    lookback_seconds: int = DEFAULT_HISTORY_LOOKBACK_SECONDS
    step_seconds: int = DEFAULT_HISTORY_STEP_SECONDS
    interval_seconds: int = DEFAULT_HISTORY_STEP_SECONDS
    rate_limit_per_minute: int = 60
    #: What every reading from this source is stored as. Numbers, because a
    #: metrics system answers with numbers; a state signal from a metrics system
    #: is a number somebody has decided means a word.
    kind: SignalKind = field(default=SignalKind.NUMBER)

    def __post_init__(self) -> None:
        if self.lookback_seconds > MAX_HISTORY_LOOKBACK_SECONDS:
            raise BridgeBoundExceeded(
                parameter=f"{self.signal_name} history lookback",
                requested=self.lookback_seconds,
                limit=MAX_HISTORY_LOOKBACK_SECONDS,
                constant="MAX_HISTORY_LOOKBACK_SECONDS",
            )
        if self.step_seconds <= 0:
            raise ValueError(
                f"{self.signal_name} declares a history step of {self.step_seconds}s. A step "
                f"of zero is a query for every sample the source holds."
            )

    @property
    def declaration(self) -> SignalDeclaration:
        """Return what this source says about itself."""
        return SignalDeclaration(
            source=BRIDGE_SOURCE,
            signals=(self.signal_name,),
            interval_seconds=self.interval_seconds,
            rate_limit_per_minute=self.rate_limit_per_minute,
            max_provider_calls=1,
        )

    async def read(
        self,
        *,
        resource_ids: tuple[str, ...],
        at: datetime,
        budget: PollBudget,
    ) -> SignalPage:
        """Return the history this source holds for ``resource_ids`` as at ``at``.

        One provider call whatever the estate's size: a range query covers every
        series the matcher selects at once, which is what keeps this source's
        cost independent of how many resources a detector watches.

        Raises whatever the metrics system raises when it cannot answer.
        """
        series = await self.metrics.history(
            matchers=(self.matcher,),
            start=at - timedelta(seconds=self.lookback_seconds),
            end=at,
            step_seconds=self.step_seconds,
        )
        mapping = map_series(series, rules=self.rules, estate=self.estate)
        wanted = set(resource_ids)
        readings = [
            reading
            for entry in mapping.mapped
            if not wanted or entry.resource_id in wanted
            for reading in self._readings(entry)
        ]
        return SignalPage(readings=tuple(readings[: budget.max_readings]), provider_calls=1)

    async def mapping_for(self, *, at: datetime) -> SeriesMapping:
        """Return the mapping of the series this source reads, for a coverage report.

        Separate from ``read`` because a mapping report is a thing an operator
        asks for and a poll is a thing the tick does; making the poll return both
        would mean every tick paying for a report nobody reads.
        """
        series = await self.metrics.series(matchers=(self.matcher,), at=at)
        return map_series(series, rules=self.rules, estate=self.estate)

    def _readings(self, entry: MappedSeries) -> tuple[SignalReading, ...]:
        """Return one reading per sample of one mapped series."""
        labels = {
            **entry.labels,
            PROVENANCE_LABEL: BRIDGE_SOURCE,
            VIEW_LABEL: entry.view.value,
        }
        return tuple(
            SignalReading(
                name=self.signal_name,
                resource_id=entry.resource_id,
                kind=self.kind,
                value=point.value,
                labels=labels,
                observed_at=point.observed_at,
            )
            for point in entry.series.samples[:MAX_HISTORY_SAMPLES]
        )


__all__ = ["PROVENANCE_LABEL", "VIEW_LABEL", "MetricsHistorySource"]
