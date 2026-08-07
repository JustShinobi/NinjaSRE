"""SC-004: a synthetic high-cardinality workload does not become a collector outage.

The unit tests prove the guard collapses values. This proves the property that
actually matters, which is a different one: that a *deployment* under a workload
designed to be pathological emits a bounded number of time series, and that the
totals still add up afterwards.

The workload is the one that happens in reality — every investigation carrying
its own run identifier into a label, which is the mistake this whole mechanism
exists to survive.
"""

from __future__ import annotations

import json

import pytest

from config.constants.observability import (
    MAX_METRIC_LABEL_VALUES,
    METRIC_LABEL_OVERFLOW,
)
from platform.observability.config import TelemetryConfig
from platform.observability.export import OtlpExporter, RecordingTransport
from platform.observability.metrics.definitions import MetricRegistry

pytestmark = pytest.mark.contract

ENABLED = TelemetryConfig(endpoint="http://collector.internal:4318")

#: Twenty-five times the per-label budget. Enough that an unbounded
#: implementation is unmistakably unbounded rather than arguably slow.
SYNTHETIC_RUNS = MAX_METRIC_LABEL_VALUES * 25


def test_a_pathological_label_stays_within_its_budget() -> None:
    transport = RecordingTransport()
    metrics = MetricRegistry(config=ENABLED, exporter=OtlpExporter(ENABLED, transport))
    counter = metrics.counter("investigation.count")

    for run in range(SYNTHETIC_RUNS):
        counter.add(1, team=f"team-{run}", trigger="alert", outcome="resolved")

    metrics.flush()
    points = json.loads(transport.sent[0][1])["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][
        0
    ]["sum"]["dataPoints"]

    assert len(points) == MAX_METRIC_LABEL_VALUES + 1


def test_the_total_still_adds_up_after_the_collapse() -> None:
    """A bound that lost counts would be a bound nobody could trust a bill to."""
    metrics = MetricRegistry(config=ENABLED, exporter=OtlpExporter(ENABLED, RecordingTransport()))
    counter = metrics.counter("investigation.count")

    for run in range(SYNTHETIC_RUNS):
        counter.add(1, team=f"team-{run}")

    assert sum(counter.points.values()) == SYNTHETIC_RUNS
    assert counter.value(team=METRIC_LABEL_OVERFLOW) == SYNTHETIC_RUNS - MAX_METRIC_LABEL_VALUES


def test_every_instrument_holds_its_own_budget_under_the_same_load() -> None:
    """One instrument's overflow must not spend another's."""
    metrics = MetricRegistry(config=ENABLED, exporter=OtlpExporter(ENABLED, RecordingTransport()))
    investigations = metrics.counter("investigation.count")
    recalls = metrics.counter("memory.recalls")

    for run in range(SYNTHETIC_RUNS):
        investigations.add(1, team=f"team-{run}")
    recalls.add(1, team="platform")

    assert recalls.value(team="platform") == 1
    assert len(recalls.points) == 1


def test_the_whole_document_stays_bounded_across_every_family() -> None:
    """The number a collector cares about is series per scrape, not per instrument."""
    transport = RecordingTransport()
    metrics = MetricRegistry(config=ENABLED, exporter=OtlpExporter(ENABLED, transport))

    for run in range(SYNTHETIC_RUNS):
        metrics.counter("investigation.count").add(1, team=f"team-{run}")
        metrics.counter("capability.invocations").add(1, capability=f"tool-{run}")
        metrics.histogram("capability.duration").record(0.1, capability=f"tool-{run}")
        metrics.counter("llm.cost_usd").add(0.01, team=f"team-{run}", model=f"model-{run}")

    metrics.flush()
    document = json.loads(transport.sent[0][1])
    series = sum(
        len(
            metric.get("sum", metric.get("gauge", metric.get("histogram", {}))).get(
                "dataPoints", []
            )
        )
        for metric in document["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]
    )

    #: Four instruments, one bounded label each except cost, which has two —
    #: and the two are correlated in this workload, so the pairs are bounded by
    #: the first to overflow rather than by their product.
    assert series <= 5 * (MAX_METRIC_LABEL_VALUES + 1)


def test_the_guard_reports_the_collapse_where_an_operator_will_see_it() -> None:
    """A bound that was silent would look like a bug in the dashboard."""
    metrics = MetricRegistry(config=ENABLED, exporter=OtlpExporter(ENABLED, RecordingTransport()))
    for run in range(SYNTHETIC_RUNS):
        metrics.counter("investigation.count").add(1, team=f"team-{run}")

    record = metrics.guard.to_record()

    assert record["overflowed"] == [
        {
            "instrument": "investigation.count",
            "label": "team",
            "collapsed": SYNTHETIC_RUNS - MAX_METRIC_LABEL_VALUES,
        }
    ]
