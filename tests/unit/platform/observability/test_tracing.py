"""One investigation is one trace, across every boundary it crosses.

The boundary that matters most is the sub-agent one, because that is where a
naive implementation loses the thread: the sub-agent gets its own root span, the
trace splits in two, and the operator looking at a slow investigation sees half
of it. So the propagation tests are about identity — the child's trace id is the
parent's — rather than about a span existing.

The second is the external call. A vendor that speaks W3C trace-context can join
the trace; one that does not still gets the correlation identifier in a header,
because an operator correlating our logs with a vendor's needs one shared string
and it does not have to be a trace id.
"""

from __future__ import annotations

import json

import pytest

from config.constants.observability import (
    CORRELATION_HEADER,
    SPAN_ID_HEX_DIGITS,
    TRACE_ID_HEX_DIGITS,
    TRACEPARENT_HEADER,
)
from platform.observability.config import TelemetryConfig
from platform.observability.export import OtlpExporter, RecordingTransport
from platform.observability.tracing import SpanContext, SpanKind, SpanStatus, Tracer

pytestmark = pytest.mark.unit

ENABLED = TelemetryConfig(endpoint="http://collector.internal:4318")


def tracer(config: TelemetryConfig = ENABLED) -> Tracer:
    """Return a tracer whose exporter records rather than sends."""
    return Tracer(config=config, exporter=OtlpExporter(config, RecordingTransport()))


def test_a_span_is_recorded_with_its_kind_and_attributes() -> None:
    traced = tracer()

    with traced.span("pipeline.triage", SpanKind.PIPELINE_STAGE, team="platform") as span:
        span.set_attribute("evidence", "17")

    finished = traced.finished[0]
    assert finished.name == "pipeline.triage"
    assert finished.kind is SpanKind.PIPELINE_STAGE
    assert finished.attributes == {"team": "platform", "evidence": "17"}
    assert finished.status is SpanStatus.OK
    assert finished.duration_ns > 0


def test_every_boundary_the_feature_names_has_a_kind() -> None:
    """FR-009 names five; an external call is the sixth, for FR-010."""
    assert sorted(kind.value for kind in SpanKind) == [
        "capability",
        "external_call",
        "loop_iteration",
        "pipeline_stage",
        "storage",
        "sub_agent",
    ]


def test_a_nested_span_is_a_child_of_the_one_it_opened_inside() -> None:
    traced = tracer()

    with (
        traced.span("pipeline.triage", SpanKind.PIPELINE_STAGE) as outer,
        traced.span("grafana.query", SpanKind.CAPABILITY) as inner,
    ):
        pass

    assert inner.parent_span_id == outer.context.span_id
    assert inner.context.trace_id == outer.context.trace_id


def test_the_stack_unwinds_so_siblings_are_siblings() -> None:
    traced = tracer()

    with traced.span("loop", SpanKind.LOOP_ITERATION) as root:
        with traced.span("first", SpanKind.CAPABILITY) as first:
            pass
        with traced.span("second", SpanKind.CAPABILITY) as second:
            pass

    assert first.parent_span_id == second.parent_span_id == root.context.span_id


def test_there_is_no_current_span_once_the_block_ends() -> None:
    traced = tracer()

    with traced.span("pipeline.triage", SpanKind.PIPELINE_STAGE):
        assert traced.current() is not None

    assert traced.current() is None


def test_an_exception_is_recorded_and_re_raised() -> None:
    """A stage records its exception and re-raises: the trace is not a swallow point."""
    traced = tracer()

    with (
        pytest.raises(RuntimeError, match="grafana said no"),
        traced.span("grafana.query", SpanKind.CAPABILITY),
    ):
        raise RuntimeError("grafana said no")

    span = traced.finished[0]
    assert span.status is SpanStatus.ERROR
    assert "grafana said no" in span.error
    assert span.ended_ns > 0


def test_an_investigation_names_the_trace_after_its_correlation_identifier() -> None:
    traced = tracer()

    with (
        traced.investigation("inv-2026-08-07-001") as context,
        traced.span("pipeline.triage", SpanKind.PIPELINE_STAGE) as span,
    ):
        assert span.context.correlation_id == "inv-2026-08-07-001"

    assert context.correlation_id == "inv-2026-08-07-001"


def test_opening_an_investigation_correlates_the_logs_as_well_as_the_trace() -> None:
    """FR-012: one call binds both signals, so no deployment makes only one of them."""
    from platform.observability.logging import current_correlation_id

    traced = tracer()

    with traced.investigation("inv-log-1"):
        assert current_correlation_id() == "inv-log-1"

    assert current_correlation_id() == ""


def test_the_correlation_identifier_survives_a_sub_agent_boundary() -> None:
    """FR-010. The failure this catches is a sub-agent starting its own trace."""
    parent = tracer()

    with (
        parent.investigation("inv-77") as context,
        parent.span("dispatch", SpanKind.SUB_AGENT) as dispatch,
    ):
        carried = parent.carrier()

    child = tracer()
    with (
        child.adopt(SpanContext.from_carrier(carried)),
        child.span("sub.pipeline.triage", SpanKind.PIPELINE_STAGE) as inside,
    ):
        pass

    assert inside.context.trace_id == context.trace_id
    assert inside.context.correlation_id == "inv-77"
    assert inside.parent_span_id == dispatch.context.span_id


def test_a_sub_agent_that_was_handed_nothing_starts_its_own_trace() -> None:
    """Rather than raising: a sub-agent must run whether or not it was traced."""
    child = tracer()

    with (
        child.adopt(None),
        child.span("sub.pipeline.triage", SpanKind.PIPELINE_STAGE) as inside,
    ):
        pass

    assert inside.context.trace_id
    assert inside.parent_span_id == ""


def test_headers_carry_w3c_trace_context_and_the_correlation_identifier() -> None:
    """T012: propagation into external calls where the protocol allows."""
    traced = tracer()

    with (
        traced.investigation("inv-77"),
        traced.span("vendor.call", SpanKind.EXTERNAL_CALL) as span,
    ):
        headers = traced.headers()

    assert headers[CORRELATION_HEADER] == "inv-77"
    version, trace_id, span_id, flags = headers[TRACEPARENT_HEADER].split("-")
    assert version == "00"
    assert trace_id == span.context.trace_id
    assert span_id == span.context.span_id
    assert flags == "01"


def test_headers_outside_a_span_are_empty_rather_than_invented() -> None:
    assert tracer().headers() == {}


def test_a_traceparent_from_outside_is_joined_rather_than_replaced() -> None:
    incoming = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    traced = tracer()

    with (
        traced.adopt(SpanContext.parse(incoming, correlation_id="inv-9")),
        traced.span("gateway.request", SpanKind.PIPELINE_STAGE) as span,
    ):
        pass

    assert span.context.trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert span.parent_span_id == "00f067aa0ba902b7"
    assert span.context.correlation_id == "inv-9"


@pytest.mark.parametrize(
    "header",
    ["", "nonsense", "00-tooshort-00f067aa0ba902b7-01", "00-4bf92f3577b34da6a3ce929d0e0e4736-01"],
)
def test_a_malformed_traceparent_is_ignored_rather_than_fatal(header: str) -> None:
    assert SpanContext.parse(header) is None


def test_identifiers_are_the_widths_the_protocol_fixes() -> None:
    traced = tracer()

    with traced.span("a", SpanKind.CAPABILITY) as span:
        pass

    assert len(span.context.trace_id) == TRACE_ID_HEX_DIGITS
    assert len(span.context.span_id) == SPAN_ID_HEX_DIGITS


def test_a_disabled_deployment_records_no_span_at_all() -> None:
    traced = tracer(TelemetryConfig())

    with traced.span("pipeline.triage", SpanKind.PIPELINE_STAGE):
        pass

    assert traced.finished == []
    assert traced.flush() == 0


def test_an_unsampled_trace_is_not_recorded() -> None:
    traced = Tracer(
        config=TelemetryConfig(endpoint="http://collector:4318", sample_ratio=0.0),
        exporter=OtlpExporter(TelemetryConfig(endpoint="http://collector:4318")),
    )

    with traced.span("pipeline.triage", SpanKind.PIPELINE_STAGE):
        pass

    assert traced.finished == []


def test_flushing_produces_one_otlp_document_holding_every_span() -> None:
    transport = RecordingTransport()
    traced = Tracer(config=ENABLED, exporter=OtlpExporter(ENABLED, transport))

    with (
        traced.investigation("inv-1"),
        traced.span("pipeline.triage", SpanKind.PIPELINE_STAGE, team="platform"),
        traced.span("episodes.search", SpanKind.STORAGE),
    ):
        pass

    assert traced.flush() == 1
    assert traced.finished == []

    document = json.loads(transport.sent[0][1])
    spans = document["resourceSpans"][0]["scopeSpans"][0]["spans"]
    assert {span["name"] for span in spans} == {"pipeline.triage", "episodes.search"}
    assert all(span["traceId"] for span in spans)
    assert transport.sent[0][0].endswith("/v1/traces")


def test_a_span_carries_the_correlation_identifier_as_an_attribute() -> None:
    """So a collector can find one investigation without knowing our trace ids."""
    transport = RecordingTransport()
    traced = Tracer(config=ENABLED, exporter=OtlpExporter(ENABLED, transport))

    with (
        traced.investigation("inv-42"),
        traced.span("pipeline.triage", SpanKind.PIPELINE_STAGE),
    ):
        pass
    traced.flush()

    span = json.loads(transport.sent[0][1])["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    attributes = {entry["key"]: entry["value"]["stringValue"] for entry in span["attributes"]}
    assert attributes["correlation_id"] == "inv-42"


def test_a_flush_the_collector_refuses_still_clears_the_buffer() -> None:
    """Otherwise a collector outage grows a span buffer inside the investigation."""

    class Dead:
        def send(self, url: str, body: bytes, headers: dict[str, str], *, timeout: float) -> None:
            raise TimeoutError("the collector did not answer")

    exporter = OtlpExporter(ENABLED, Dead())
    traced = Tracer(config=ENABLED, exporter=exporter)
    with traced.span("pipeline.triage", SpanKind.PIPELINE_STAGE):
        pass

    assert traced.flush() == 0
    assert traced.finished == []
    assert exporter.dropped == 1
