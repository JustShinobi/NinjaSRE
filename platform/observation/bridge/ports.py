"""What the bridge needs a metrics, log, dashboard or rule source to be able to do.

Four protocols and four value types, and every one of them is deliberately
smaller than the system behind it. Prometheus can do arithmetic over ranges;
Loki has a query language; Grafana has an API with a hundred routes. None of
that is here, because a bridge that exposed the full surface of four vendors
would be four vendors' worth of behaviour to keep working, and the join this
feature exists to make needs almost none of it.

**The protocols are here rather than in ``integrations/`` for the tier rule.**
Tier 3 cannot import tier 2, and the bridge is tier 3. An integration that can
answer these implements them and a composition root hands one over — the same
shape the signal reader and the discovery source already use, for the same
reason.

**Nothing here can carry a credential.** There is no constructor argument on a
protocol and no parameter a token fits in. An implementation reaches its
provider through ``integrations/_base/client.py``, which resolves a
tenant-scoped handle and lets the proxy inject the secret at the network edge.

**A source that cannot answer raises.** Returning nothing would be
indistinguishable from a source that answered and had nothing to say, and those
two produce opposite conclusions. Every docstring below says so, because the
next implementation will be written from the docstring.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class MetricPoint:
    """One sample of one series: when, and what."""

    observed_at: datetime
    value: float


@dataclass(frozen=True, slots=True)
class MetricSeries:
    """One series as the metrics system describes it.

    ``labels`` is the source's own label set, unmodified. Mapping it to an estate
    resource happens in ``mapping.py`` against declared rules, and doing it here
    would mean the transport deciding a join it has no way to validate.
    """

    metric: str
    labels: Mapping[str, str] = field(default_factory=dict)
    samples: tuple[MetricPoint, ...] = ()

    @property
    def newest(self) -> MetricPoint | None:
        """Return the most recent sample, or ``None`` for a series with none."""
        return max(self.samples, key=lambda point: point.observed_at) if self.samples else None


@dataclass(frozen=True, slots=True)
class LogLine:
    """One line a log system returned, with the stream it came from."""

    observed_at: datetime
    line: str
    labels: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AlertRule:
    """One alerting rule the operator already wrote.

    Carried in the source's own terms — its file, its group, its expression —
    because the whole point of reading these is to show an operator their own
    rule beside a shipped detector that covers the same condition. A normalised
    form would show them something they never wrote.
    """

    name: str
    expression: str
    group: str = ""
    source_file: str = ""
    for_seconds: int = 0
    labels: Mapping[str, str] = field(default_factory=dict)
    annotations: Mapping[str, str] = field(default_factory=dict)


@runtime_checkable
class MetricsSource(Protocol):
    """A metrics system that can be asked which series exist and what they held."""

    async def series(
        self,
        *,
        matchers: tuple[str, ...],
        at: datetime,
    ) -> tuple[MetricSeries, ...]:
        """Return the series matching ``matchers`` as at ``at``, newest sample each.

        ``matchers`` are the source's own selectors, opaque here. This package
        neither parses nor validates one, because a bridge that could express
        arbitrary computation in a selector would be the second query language
        the deployment has to keep working.

        Raises ``MetricsSourceUnreachable`` when the system did not answer. An
        empty tuple means it answered and has nothing matching, which is a
        different fact and leads to a different conclusion.
        """

    async def history(
        self,
        *,
        matchers: tuple[str, ...],
        start: datetime,
        end: datetime,
        step_seconds: int,
    ) -> tuple[MetricSeries, ...]:
        """Return what ``matchers`` held between ``start`` and ``end``, at ``step_seconds``.

        This is the method that makes the bridge worth having: a detector can
        conclude something about a window during which the deployment's own
        poller was not running, which no amount of local polling can recover.

        Raises ``MetricsSourceUnreachable`` when the system did not answer.
        """


@runtime_checkable
class LogSource(Protocol):
    """A log system that can be asked for one stream over one bounded window."""

    async def retention_seconds(self) -> int:
        """Return how far back this source can answer, or zero if it does not say.

        Zero is "it has no opinion", not "it keeps nothing". A caller that read
        zero as no retention would refuse every query against a source that
        simply does not publish the number.
        """

    async def lines(
        self,
        *,
        selector: str,
        start: datetime,
        end: datetime,
        limit: int,
    ) -> tuple[LogLine, ...]:
        """Return up to ``limit`` lines matching ``selector`` between the two instants.

        The selector is the source's own stream selector, opaque here for the
        reason a metric matcher is.

        Raises ``LogSourceUnreachable`` when the system did not answer.
        """


@runtime_checkable
class DashboardSource(Protocol):
    """A dashboard system, asked only whether a link to it would work."""

    async def check(self) -> None:
        """Return normally when a reader could open a dashboard here.

        Raises ``DashboardsUnreachable`` when they could not — which includes
        authentication this deployment does not hold, because a link that answers
        with a login page is a dead end wearing the appearance of an answer.
        """


@runtime_checkable
class AlertRuleSource(Protocol):
    """A rule system that can list the alerting rules an operator already wrote."""

    async def rules(self) -> tuple[AlertRule, ...]:
        """Return every alerting rule the source holds.

        Raises ``MetricsSourceUnreachable`` when it did not answer. Read so that
        a shipped detector covering a condition the operator already alerts on
        can be reported as a duplicate rather than shipped as a second alarm.
        """


__all__ = [
    "AlertRule",
    "AlertRuleSource",
    "DashboardSource",
    "LogLine",
    "LogSource",
    "MetricPoint",
    "MetricSeries",
    "MetricsSource",
]
