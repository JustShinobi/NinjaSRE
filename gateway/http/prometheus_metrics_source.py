"""Prometheus as the bridge's ``MetricsSource``: series now, and history since.

Composed here rather than in ``integrations/prometheus/`` because it has to
import both sides of a boundary this repository draws deliberately: the
hypervisor integration and the rest of the catalogue must work with no bridge
configured at all, so nothing under ``integrations/`` may import
``platform.observation.bridge``. A composition root is exactly the place
allowed to hold both — the vendor's own client and the bridge's own value
types — and ``gateway/http/discovery_sources.py`` already does for
``PrometheusMetrics`` beside this.

**A failed call raises.** An unreachable Prometheus and an empty answer are
opposite facts to a detector reading through this, so a client failure becomes
``MetricsSourceUnreachable`` rather than an empty tuple.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from integrations._base.errors import IntegrationError
from integrations.prometheus.client import PrometheusClient
from platform.observation.bridge.errors import MetricsSourceUnreachable
from platform.observation.bridge.ports import MetricPoint, MetricSeries

#: The label every Prometheus vector and matrix result carries the metric's own
#: name under. Popped off the label set rather than left in it, because
#: ``MetricSeries.metric`` is where the rest of this codebase reads it from.
_NAME_LABEL = "__name__"


@dataclass(frozen=True, slots=True)
class PrometheusMetricsSource:
    """Answers the bridge's ``series``/``history`` questions over one client."""

    client: PrometheusClient

    async def series(
        self,
        *,
        matchers: tuple[str, ...],
        at: datetime,
    ) -> tuple[MetricSeries, ...]:
        """Return the newest sample of every series each matcher selects, now.

        ``at`` is not sent to Prometheus: an instant query with no explicit
        time asks for now, which is what every caller of this method wants —
        a caller after a specific instant in the past wants ``history``.
        """
        del at
        found: list[MetricSeries] = []
        try:
            for matcher in matchers:
                for row in await self.client.query_instant(matcher):
                    series = _instant_series(row)
                    if series is not None:
                        found.append(series)
        except IntegrationError as error:
            raise MetricsSourceUnreachable(self.client.integration, reason=str(error)) from error
        return tuple(found)

    async def history(
        self,
        *,
        matchers: tuple[str, ...],
        start: datetime,
        end: datetime,
        step_seconds: int,
    ) -> tuple[MetricSeries, ...]:
        """Return what every matcher held between ``start`` and ``end``."""
        found: list[MetricSeries] = []
        try:
            for matcher in matchers:
                rows = await self.client.query_range(
                    matcher,
                    start=str(int(start.timestamp())),
                    end=str(int(end.timestamp())),
                    step=f"{step_seconds}s",
                )
                for row in rows:
                    series = _range_series(row)
                    if series is not None:
                        found.append(series)
        except IntegrationError as error:
            raise MetricsSourceUnreachable(self.client.integration, reason=str(error)) from error
        return tuple(found)


def _instant_series(row: Mapping[str, Any]) -> MetricSeries | None:
    """Return one instant-query row as a series holding its one sample."""
    metric, labels = _metric_and_labels(row)
    point = _point(row.get("value"))
    if metric is None or point is None:
        return None
    return MetricSeries(metric=metric, labels=labels, samples=(point,))


def _range_series(row: Mapping[str, Any]) -> MetricSeries | None:
    """Return one range-query row as a series holding every sample in the window."""
    metric, labels = _metric_and_labels(row)
    if metric is None:
        return None
    values = row.get("values")
    if not isinstance(values, list):
        values = []
    points = tuple(point for point in (_point(entry) for entry in values) if point is not None)
    return MetricSeries(metric=metric, labels=labels, samples=points)


def _metric_and_labels(row: Mapping[str, Any]) -> tuple[str | None, dict[str, str]]:
    """Return the metric name and the remaining labels from one result row."""
    raw = row.get("metric")
    if not isinstance(raw, dict):
        return None, {}
    labels = {str(key): str(value) for key, value in raw.items() if key != _NAME_LABEL}
    name = raw.get(_NAME_LABEL)
    return (str(name) if name else None), labels


def _point(sample: Any) -> MetricPoint | None:
    """Return one ``[timestamp, "value"]`` pair as a point, or ``None`` if malformed."""
    if not isinstance(sample, list) or len(sample) != 2:
        return None
    try:
        observed_at = datetime.fromtimestamp(float(sample[0]), tz=UTC)
        value = float(sample[1])
    except (TypeError, ValueError):
        return None
    return MetricPoint(observed_at=observed_at, value=value)


__all__ = ["PrometheusMetricsSource"]
