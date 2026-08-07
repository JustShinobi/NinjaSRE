"""Every metric family the operator was promised, and no label they were not.

FR-006 names eight families. A test that asserted "the registry has instruments"
would pass on any subset of them, so this asserts the families by name and the
label set of each one by content — the second half being the part that decays,
because adding a label is a one-word change nobody reviews as a cardinality
decision.
"""

from __future__ import annotations

import pytest

from platform.observability.config import TelemetryConfig
from platform.observability.export import OtlpExporter, RecordingTransport
from platform.observability.metrics.cardinality import UnknownLabel
from platform.observability.metrics.definitions import (
    DEFINITIONS,
    MetricFamily,
    MetricRegistry,
    definition_for,
)

pytestmark = pytest.mark.unit

ENABLED = TelemetryConfig(endpoint="http://collector.internal:4318")


def registry(config: TelemetryConfig = ENABLED) -> MetricRegistry:
    """Return a registry writing into a transport that records rather than sends."""
    return MetricRegistry(config=config, exporter=OtlpExporter(config, RecordingTransport()))


def test_all_eight_families_are_declared() -> None:
    assert {definition.family for definition in DEFINITIONS} == set(MetricFamily)


def test_the_families_are_the_ones_the_operator_was_promised() -> None:
    assert sorted(family.value for family in MetricFamily) == [
        "approval",
        "capability",
        "cost",
        "guardrail",
        "integration",
        "investigation",
        "memory",
        "scheduler",
    ]


def test_every_family_covers_what_it_was_asked_to_cover() -> None:
    """FR-006, family by family, so a dropped instrument fails rather than passes."""
    by_family: dict[MetricFamily, set[str]] = {}
    for definition in DEFINITIONS:
        by_family.setdefault(definition.family, set()).add(definition.name)

    assert by_family[MetricFamily.INVESTIGATION] >= {
        "investigation.count",
        "investigation.duration",
        "investigation.outcome",
    }
    assert by_family[MetricFamily.COST] >= {
        "llm.input_tokens",
        "llm.output_tokens",
        "llm.cached_tokens",
        "llm.cost_usd",
    }
    assert by_family[MetricFamily.CAPABILITY] >= {
        "capability.invocations",
        "capability.failures",
        "capability.duration",
    }
    assert by_family[MetricFamily.INTEGRATION] >= {
        "integration.health",
        "integration.verifications",
    }
    assert by_family[MetricFamily.SCHEDULER] >= {
        "scheduler.queue_depth",
        "scheduler.claim_latency",
        "scheduler.misfires",
    }
    assert by_family[MetricFamily.APPROVAL] >= {
        "approval.pending",
        "approval.decision_latency",
        "approval.outcome",
    }
    assert by_family[MetricFamily.GUARDRAIL] >= {"guardrail.actions"}
    assert by_family[MetricFamily.MEMORY] >= {
        "memory.recalls",
        "memory.recall_hits",
        "memory.episodes_written",
    }


def test_every_definition_says_what_it_measures_and_in_what_unit() -> None:
    for definition in DEFINITIONS:
        assert definition.description.strip(), definition.name
        assert definition.description.strip().endswith("."), definition.name
        assert definition.unit, definition.name


def test_names_are_unique() -> None:
    names = [definition.name for definition in DEFINITIONS]

    assert len(names) == len(set(names))


def test_no_instrument_declares_an_unbounded_dimension() -> None:
    """The list is short on purpose. Adding to it is the review this test forces."""
    permitted = {
        "team",
        "trigger",
        "outcome",
        "model",
        "provider",
        "capability",
        "outcome_class",
        "integration",
        "status",
        "side_effect_level",
        "rule",
        "action",
    }
    declared = {name for definition in DEFINITIONS for name in definition.labels.names}

    assert declared <= permitted, f"undeclared dimensions: {sorted(declared - permitted)}"


def test_the_scheduler_family_carries_no_labels_at_all() -> None:
    """Queue depth is a property of the deployment, not of a team."""
    assert definition_for("scheduler.queue_depth").labels.names == ()


def test_an_undeclared_instrument_cannot_be_created() -> None:
    with pytest.raises(KeyError, match="pod.count"):
        registry().counter("pod.count")


def test_an_undeclared_label_is_refused_at_the_write() -> None:
    with pytest.raises(UnknownLabel, match="pod"):
        registry().counter("investigation.count").add(1, team="platform", pod="checkout-7d9f")


def test_a_counter_accumulates_per_series() -> None:
    counter = registry().counter("investigation.count")
    counter.add(1, team="platform", outcome="resolved")
    counter.add(2, team="platform", outcome="resolved")
    counter.add(5, team="payments", outcome="resolved")

    assert counter.value(team="platform", outcome="resolved") == 3
    assert counter.value(team="payments", outcome="resolved") == 5


def test_a_gauge_records_the_latest_value_rather_than_a_sum() -> None:
    gauge = registry().gauge("scheduler.queue_depth")
    gauge.set(9)
    gauge.set(4)

    assert gauge.value() == 4


def test_a_histogram_records_count_and_sum() -> None:
    histogram = registry().histogram("investigation.duration")
    histogram.record(2.0, team="platform")
    histogram.record(4.0, team="platform")

    assert histogram.count(team="platform") == 2
    assert histogram.total(team="platform") == 6.0


def test_the_same_instrument_is_returned_twice() -> None:
    """Two objects for one name would be two half-filled sets of series."""
    metrics = registry()

    assert metrics.counter("investigation.count") is metrics.counter("investigation.count")


def test_asking_for_an_instrument_by_the_wrong_kind_is_refused() -> None:
    with pytest.raises(TypeError, match="investigation.duration"):
        registry().counter("investigation.duration")


def test_a_disabled_deployment_records_nothing_at_all() -> None:
    """Not "records and discards" — a disabled deployment does no work."""
    metrics = registry(TelemetryConfig())
    metrics.counter("investigation.count").add(1, team="platform")

    assert metrics.snapshot() == []
    assert metrics.flush() == 0


def test_flushing_produces_one_otlp_document_the_collector_accepts() -> None:
    transport = RecordingTransport()
    metrics = MetricRegistry(config=ENABLED, exporter=OtlpExporter(ENABLED, transport))
    metrics.counter("investigation.count").add(1, team="platform", outcome="resolved")
    metrics.gauge("scheduler.queue_depth").set(3)
    metrics.histogram("investigation.duration").record(1.5, team="platform")

    assert metrics.flush() == 1

    url, body, _ = transport.sent[0]
    assert url.endswith("/v1/metrics")

    import json

    document = json.loads(body)
    resource = document["resourceMetrics"][0]
    assert resource["resource"]["attributes"] == [
        {"key": "service.name", "value": {"stringValue": "ninjasre"}}
    ]
    emitted = {metric["name"] for metric in resource["scopeMetrics"][0]["metrics"]}
    assert emitted == {"investigation.count", "scheduler.queue_depth", "investigation.duration"}


def test_a_flush_carries_the_shapes_otlp_defines_for_each_kind() -> None:
    import json

    transport = RecordingTransport()
    metrics = MetricRegistry(config=ENABLED, exporter=OtlpExporter(ENABLED, transport))
    metrics.counter("investigation.count").add(2, team="platform")
    metrics.gauge("scheduler.queue_depth").set(7)
    metrics.histogram("investigation.duration").record(1.5, team="platform")
    metrics.flush()

    by_name = {
        metric["name"]: metric
        for metric in json.loads(transport.sent[0][1])["resourceMetrics"][0]["scopeMetrics"][0][
            "metrics"
        ]
    }

    assert by_name["investigation.count"]["sum"]["isMonotonic"] is True
    assert by_name["investigation.count"]["sum"]["dataPoints"][0]["asDouble"] == 2.0
    assert by_name["scheduler.queue_depth"]["gauge"]["dataPoints"][0]["asDouble"] == 7.0
    point = by_name["investigation.duration"]["histogram"]["dataPoints"][0]
    assert point["count"] == 1
    assert point["sum"] == 1.5
    assert sum(point["bucketCounts"]) == 1


def test_a_flush_that_the_collector_refuses_does_not_raise() -> None:
    class Dead:
        def send(self, url: str, body: bytes, headers: dict[str, str], *, timeout: float) -> None:
            raise ConnectionRefusedError("the collector is gone")

    exporter = OtlpExporter(ENABLED, Dead())
    metrics = MetricRegistry(config=ENABLED, exporter=exporter)
    metrics.counter("investigation.count").add(1, team="platform")

    assert metrics.flush() == 0
    assert exporter.dropped == 1
