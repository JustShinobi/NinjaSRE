"""SC-002: with a collector configured, all of it turns up.

The claim in the specification is a list — eight metric families, five span
boundaries — and the honest way to test a list is against the list. So this
drives one investigation-shaped workload through the whole instrumentation
surface and then reads the exported OTLP documents back, asserting that every
declared instrument and every declared boundary is present in what the collector
would have received.

Read back from the wire rather than from the registry on purpose. An instrument
that accumulates points and never encodes is an instrument that shows up in a
unit test and never in a dashboard.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from platform.observability.config import TelemetryConfig
from platform.observability.export import OtlpExporter, RecordingTransport
from platform.observability.metrics.definitions import DEFINITIONS, MetricRegistry
from platform.observability.tracing import SpanKind, Tracer

pytestmark = pytest.mark.contract

ENABLED = TelemetryConfig(endpoint="http://collector.internal:4318")


def _drive_everything() -> tuple[RecordingTransport, MetricRegistry, Tracer]:
    """Run one investigation-shaped workload through every instrument and boundary."""
    transport = RecordingTransport()
    exporter = OtlpExporter(ENABLED, transport)
    metrics = MetricRegistry(config=ENABLED, exporter=exporter)
    tracer = Tracer(config=ENABLED, exporter=exporter)

    with tracer.investigation("inv-sc-002"):
        with (
            tracer.span("pipeline.triage", SpanKind.PIPELINE_STAGE, team="platform"),
            tracer.span("episodes.search", SpanKind.STORAGE, store="episodes"),
        ):
            metrics.counter("memory.recalls").add(1, team="platform")
            metrics.counter("memory.recall_hits").add(1, team="platform")
        with tracer.span("loop.iteration", SpanKind.LOOP_ITERATION):
            with tracer.span("grafana.query", SpanKind.CAPABILITY, capability="grafana.query"):
                metrics.counter("capability.invocations").add(
                    1, capability="grafana.query", outcome_class="ok"
                )
                metrics.histogram("capability.duration").record(
                    0.4, capability="grafana.query", outcome_class="ok"
                )
            with tracer.span("vendor.call", SpanKind.EXTERNAL_CALL):
                metrics.counter("capability.failures").add(
                    1, capability="pagerduty.list", outcome_class="vendor_error"
                )
            with tracer.span("subagent.dispatch", SpanKind.SUB_AGENT):
                pass

    metrics.counter("investigation.count").add(1, team="platform", trigger="alert", outcome="ok")
    metrics.counter("investigation.outcome").add(1, team="platform", outcome="resolved")
    metrics.histogram("investigation.duration").record(41.0, team="platform", outcome="resolved")
    for name in ("llm.input_tokens", "llm.output_tokens", "llm.cached_tokens"):
        metrics.counter(name).add(100, team="platform", model="sonnet", provider="anthropic")
    metrics.counter("llm.cost_usd").add(0.02, team="platform", model="sonnet", provider="anthropic")
    metrics.counter("llm.unpriced_calls").add(1, team="platform", model="local", provider="ollama")
    metrics.gauge("integration.health").set(1, integration="grafana", status="ok")
    metrics.counter("integration.verifications").add(1, integration="grafana", status="ok")
    metrics.gauge("scheduler.queue_depth").set(4)
    metrics.histogram("scheduler.claim_latency").record(0.9)
    metrics.counter("scheduler.misfires").add(1)
    metrics.gauge("approval.pending").set(2, team="platform", side_effect_level="write_reversible")
    metrics.histogram("approval.decision_latency").record(
        90.0, team="platform", side_effect_level="write_reversible"
    )
    metrics.counter("approval.outcome").add(
        1, team="platform", side_effect_level="write_reversible"
    )
    metrics.counter("guardrail.actions").add(1, rule="aws-access-key", action="redact")
    metrics.counter("memory.episodes_written").add(1, team="platform")
    # The local model's own numbers: what the weights cost in attempts, which is
    # a different question from what the endpoint cost in money above.
    metrics.counter("model.repairs").add(
        1, model="local", provider="ollama", kind="tool_call_extracted"
    )
    metrics.counter("model.degradations").add(
        1, model="local", provider="ollama", kind="repair_budget_exhausted"
    )
    for name in ("model.loop_breaks", "model.compactions", "model.truncations"):
        metrics.counter(name).add(1, model="local", provider="ollama")

    tracer.flush()
    metrics.flush()
    return transport, metrics, tracer


def _documents(transport: RecordingTransport) -> list[dict[str, Any]]:
    """Return every OTLP document the collector received."""
    return [json.loads(body) for _, body, _ in transport.sent]


def test_every_declared_instrument_reaches_the_collector() -> None:
    transport, _, _ = _drive_everything()

    exported: set[str] = set()
    for document in _documents(transport):
        for resource in document.get("resourceMetrics", []):
            for scope in resource["scopeMetrics"]:
                exported.update(metric["name"] for metric in scope["metrics"])

    declared = {definition.name for definition in DEFINITIONS}

    assert exported == declared, f"never exported: {sorted(declared - exported)}"


def test_every_declared_boundary_reaches_the_collector() -> None:
    """FR-009's five boundaries, plus the outbound call FR-010 needs."""
    transport, _, _ = _drive_everything()

    boundaries: set[str] = set()
    for document in _documents(transport):
        for resource in document.get("resourceSpans", []):
            for scope in resource["scopeSpans"]:
                for span in scope["spans"]:
                    attributes = {
                        entry["key"]: entry["value"]["stringValue"] for entry in span["attributes"]
                    }
                    boundaries.add(attributes["ninjasre.boundary"])

    assert boundaries == {kind.value for kind in SpanKind}


def test_every_span_belongs_to_the_one_investigation() -> None:
    transport, _, _ = _drive_everything()

    traces: set[str] = set()
    correlations: set[str] = set()
    for document in _documents(transport):
        for resource in document.get("resourceSpans", []):
            for scope in resource["scopeSpans"]:
                for span in scope["spans"]:
                    traces.add(span["traceId"])
                    correlations.add(
                        {
                            entry["key"]: entry["value"]["stringValue"]
                            for entry in span["attributes"]
                        }["correlation_id"]
                    )

    assert len(traces) == 1
    assert correlations == {"inv-sc-002"}


def test_nothing_was_dropped_while_the_collector_was_answering() -> None:
    _, metrics, _ = _drive_everything()

    assert metrics.exporter.dropped == 0
    assert metrics.exporter.delivered == 2, "one traces document and one metrics document"
