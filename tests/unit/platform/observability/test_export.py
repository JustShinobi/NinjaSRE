"""A collector that is down costs an investigation nothing.

The contract this module has to hold is narrow and absolute: no export failure —
refused connection, hung socket, 500, malformed reply — may propagate to the
caller. What it may do is count itself, because a drop nobody can see is
indistinguishable from telemetry that was never generated, and an operator
debugging a missing dashboard needs to know which of the two happened.
"""

from __future__ import annotations

import json

import pytest

from config.constants.observability import (
    MAX_TELEMETRY_QUEUE_DEPTH,
    OTLP_CONTENT_TYPE,
    TelemetrySignal,
)
from platform.observability.config import TelemetryConfig
from platform.observability.export import OtlpExporter, RecordingTransport

pytestmark = pytest.mark.unit

ENABLED = TelemetryConfig(endpoint="http://collector.internal:4318")


class BrokenTransport:
    """A collector that is not there."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error or ConnectionRefusedError("connection refused")
        self.calls = 0

    def send(self, url: str, body: bytes, headers: dict[str, str], *, timeout: float) -> None:
        """Fail, the way a collector that stopped answering does."""
        self.calls += 1
        raise self.error


def test_a_disabled_deployment_never_reaches_the_transport() -> None:
    transport = RecordingTransport()
    exporter = OtlpExporter(config=TelemetryConfig(), transport=transport)

    assert exporter.export(TelemetrySignal.TRACES, {"resourceSpans": []}) is False
    assert transport.sent == []


def test_an_enabled_deployment_posts_otlp_json_to_the_configured_endpoint() -> None:
    transport = RecordingTransport()
    exporter = OtlpExporter(config=ENABLED, transport=transport)

    assert exporter.export(TelemetrySignal.METRICS, {"resourceMetrics": []}) is True

    url, body, headers = transport.sent[0]
    assert url == "http://collector.internal:4318/v1/metrics"
    assert headers["Content-Type"] == OTLP_CONTENT_TYPE
    assert json.loads(body.decode("utf-8")) == {"resourceMetrics": []}
    assert exporter.delivered == 1
    assert exporter.dropped == 0


@pytest.mark.parametrize(
    "error",
    [
        ConnectionRefusedError("refused"),
        TimeoutError("the collector did not answer"),
        OSError("no route to host"),
        RuntimeError("a library raised something nobody anticipated"),
    ],
)
def test_no_export_failure_reaches_the_caller(error: Exception) -> None:
    """SC-003. Every one of these is a real collector outage mode."""
    transport = BrokenTransport(error)
    exporter = OtlpExporter(config=ENABLED, transport=transport)

    assert exporter.export(TelemetrySignal.TRACES, {"resourceSpans": []}) is False
    assert exporter.dropped == 1
    assert exporter.delivered == 0
    assert type(error).__name__ in exporter.last_failure


def test_a_collector_outage_leaves_the_drop_count_as_the_only_evidence() -> None:
    transport = BrokenTransport()
    exporter = OtlpExporter(config=ENABLED, transport=transport)

    for _ in range(17):
        exporter.export(TelemetrySignal.LOGS, {"resourceLogs": []})

    assert exporter.dropped == 17
    assert transport.calls == 17


def test_a_recovered_collector_is_used_again_without_a_restart() -> None:
    """An exporter that latched a failure would need a restart to come back."""
    broken = BrokenTransport()
    exporter = OtlpExporter(config=ENABLED, transport=broken)
    exporter.export(TelemetrySignal.TRACES, {"resourceSpans": []})

    exporter.transport = RecordingTransport()

    assert exporter.export(TelemetrySignal.TRACES, {"resourceSpans": []}) is True
    assert (exporter.delivered, exporter.dropped) == (1, 1)


def test_an_unserialisable_document_is_dropped_rather_than_raised() -> None:
    transport = RecordingTransport()
    exporter = OtlpExporter(config=ENABLED, transport=transport)

    assert exporter.export(TelemetrySignal.TRACES, {"span": object()}) is False
    assert exporter.dropped == 1
    assert transport.sent == []


def test_the_queue_is_bounded_so_an_outage_cannot_grow_the_process() -> None:
    """FR-004: dropping is the behaviour, not an accident of running out of memory."""
    exporter = OtlpExporter(config=ENABLED, transport=BrokenTransport())

    for index in range(MAX_TELEMETRY_QUEUE_DEPTH + 100):
        exporter.queue(TelemetrySignal.TRACES, {"index": index})

    assert len(exporter.pending) == MAX_TELEMETRY_QUEUE_DEPTH
    assert exporter.pending[0][1]["index"] == 100, "the oldest records should be the dropped ones"
    assert exporter.dropped == 100


def test_flushing_a_bounded_queue_reports_what_reached_the_collector() -> None:
    transport = RecordingTransport()
    exporter = OtlpExporter(config=ENABLED, transport=transport)
    for index in range(3):
        exporter.queue(TelemetrySignal.TRACES, {"index": index})

    assert exporter.flush() == 3
    assert exporter.pending == []
    assert len(transport.sent) == 3


def test_flushing_against_a_dead_collector_still_empties_the_queue() -> None:
    """Retaining what failed is how a queue becomes unbounded by another route."""
    exporter = OtlpExporter(config=ENABLED, transport=BrokenTransport())
    for index in range(5):
        exporter.queue(TelemetrySignal.TRACES, {"index": index})

    assert exporter.flush() == 0
    assert exporter.pending == []
    assert exporter.dropped == 5


def test_the_counters_are_what_a_diagnostic_bundle_reads() -> None:
    exporter = OtlpExporter(config=ENABLED, transport=BrokenTransport())
    exporter.export(TelemetrySignal.TRACES, {})

    record = exporter.to_record()

    assert record["endpoint"] == "http://collector.internal:4318"
    assert record["delivered"] == 0
    assert record["dropped"] == 1
    assert record["last_failure"]
