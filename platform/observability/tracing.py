"""Spans across every boundary an investigation crosses, and one identifier.

An investigation is one trace. It crosses five boundaries — a pipeline stage, a
loop iteration, a capability call, a sub-agent dispatch, a storage access — and
each of them is a span kind here, so "which part was slow" is answerable without
anybody having instrumented the specific case that turned out to be slow.

**The correlation identifier is the thing that has to survive.** A trace id is
generated and means nothing to a person; the correlation identifier is the name
the investigation is known by in the run trace, in every log line, and in the
episode memory writes at the end. It rides along on every span and in every set
of outbound headers, because the operator correlating our trace with a vendor's
logs needs one shared string and it will not be a trace id.

**Propagation is explicit at the sub-agent boundary.** ``carrier()`` returns
what to hand across, and ``adopt()`` takes it on the other side. A sub-agent
handed nothing starts its own trace rather than refusing to run — losing the
thread is a degraded trace, and refusing is a failed investigation.

Current-span state lives in a ``contextvars.ContextVar``, so a task spawned
inside a span inherits it and a task spawned beside one does not.
"""

from __future__ import annotations

import random
import secrets
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final

from config.constants.observability import (
    CORRELATION_HEADER,
    LOG_CORRELATION_FIELD,
    SPAN_ID_HEX_DIGITS,
    TRACE_FLAG_SAMPLED,
    TRACE_ID_HEX_DIGITS,
    TRACEPARENT_HEADER,
    TRACEPARENT_VERSION,
    TelemetrySignal,
)
from platform.observability.config import TelemetryConfig
from platform.observability.export import OtlpExporter
from platform.observability.logging import correlated

#: The scope every span here belongs to, as the collector sees it.
INSTRUMENTATION_SCOPE: Final = "ninjasre"

#: OTLP's status codes. Unset is not used: a span this process finished either
#: completed or raised, and "unset" would hide which.
_STATUS_CODE = {"ok": 1, "error": 2}

#: OTLP's span kinds. Everything here is work this process did, which is
#: ``INTERNAL``, except an outbound call, which is ``CLIENT``.
_OTLP_KIND_INTERNAL: Final[int] = 1
_OTLP_KIND_CLIENT: Final[int] = 3


class SpanKind(StrEnum):
    """Which boundary a span sits on."""

    PIPELINE_STAGE = "pipeline_stage"
    LOOP_ITERATION = "loop_iteration"
    CAPABILITY = "capability"
    SUB_AGENT = "sub_agent"
    STORAGE = "storage"
    EXTERNAL_CALL = "external_call"


class SpanStatus(StrEnum):
    """How a span ended."""

    OK = "ok"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class SpanContext:
    """What identifies one span, and what has to cross a boundary with it."""

    trace_id: str
    span_id: str
    correlation_id: str = ""
    sampled: bool = True

    def traceparent(self) -> str:
        """Return this context as a W3C ``traceparent`` header value."""
        flags = TRACE_FLAG_SAMPLED if self.sampled else "00"
        return f"{TRACEPARENT_VERSION}-{self.trace_id}-{self.span_id}-{flags}"

    def to_carrier(self) -> dict[str, str]:
        """Return what is handed across a sub-agent boundary."""
        return {
            TRACEPARENT_HEADER: self.traceparent(),
            CORRELATION_HEADER: self.correlation_id,
        }

    @classmethod
    def from_carrier(cls, carrier: Mapping[str, str]) -> SpanContext | None:
        """Return the context a carrier describes, or nothing when it describes none."""
        return cls.parse(
            carrier.get(TRACEPARENT_HEADER, ""),
            correlation_id=carrier.get(CORRELATION_HEADER, ""),
        )

    @classmethod
    def parse(cls, header: str, *, correlation_id: str = "") -> SpanContext | None:
        """Return the context ``header`` describes, or ``None`` when malformed.

        Malformed is ignored rather than raised. An inbound header is written by
        something outside this deployment, and a caller sending a broken one
        should get an untraced request rather than a rejected one.
        """
        parts = header.split("-")
        if len(parts) != 4:
            return None
        _, trace_id, span_id, flags = parts
        if not _is_hex(trace_id, TRACE_ID_HEX_DIGITS) or not _is_hex(span_id, SPAN_ID_HEX_DIGITS):
            return None
        return cls(
            trace_id=trace_id,
            span_id=span_id,
            correlation_id=correlation_id,
            sampled=flags == TRACE_FLAG_SAMPLED,
        )


@dataclass(slots=True)
class Span:
    """One unit of work, its timing, and what it was about."""

    name: str
    kind: SpanKind
    context: SpanContext
    parent_span_id: str = ""
    started_ns: int = 0
    ended_ns: int = 0
    attributes: dict[str, str] = field(default_factory=dict)
    status: SpanStatus = SpanStatus.OK
    error: str = ""

    @property
    def duration_ns(self) -> int:
        """Return how long this span took, in nanoseconds."""
        return max(0, self.ended_ns - self.started_ns)

    def set_attribute(self, name: str, value: str) -> None:
        """Record one fact about this span.

        Span attributes are deliberately unbounded where metric labels are not.
        A pod name belongs here — one trace holds one of it, and a collector
        stores a trace rather than a time series per distinct value.
        """
        self.attributes[name] = value


@dataclass(slots=True)
class Tracer:
    """Opens spans, keeps the current one, and exports the finished ones.

    ``finished`` is a buffer rather than a stream because an investigation
    produces its spans over minutes and a collector should receive them as one
    document. It is bounded by the flush the run's end performs; a run that
    never flushed would be a run that never ended.
    """

    config: TelemetryConfig
    exporter: OtlpExporter
    clock: Any = field(default=time.time_ns)
    finished: list[Span] = field(default_factory=list)
    _stack: list[Span] = field(default_factory=list, repr=False)
    _adopted: SpanContext | None = field(default=None, repr=False)
    _random: random.Random = field(default_factory=random.Random, repr=False)

    def current(self) -> SpanContext | None:
        """Return the context of the innermost open span, if there is one."""
        if self._stack:
            return self._stack[-1].context
        return self._adopted

    def carrier(self) -> dict[str, str]:
        """Return what to hand a sub-agent so it joins this trace."""
        context = self.current()
        return context.to_carrier() if context else {}

    def headers(self) -> dict[str, str]:
        """Return the headers an outbound call carries, where the protocol allows.

        Empty outside a span, rather than a freshly minted trace id. A header
        naming a trace that holds one span is worse than no header: it looks
        like a correlation and is not one.
        """
        return self.carrier() if self.current() else {}

    @contextmanager
    def investigation(self, correlation_id: str) -> Iterator[SpanContext]:
        """Open a trace named after ``correlation_id`` for the duration of a run.

        Binds the identifier for logging too, so a module three layers down that
        never heard of this investigation still emits lines carrying its name.
        One call, both signals: the alternative is two calls and a deployment
        where somebody made only the first.
        """
        context = SpanContext(
            trace_id=self._trace_id(),
            span_id="",
            correlation_id=correlation_id,
            sampled=self._samples(),
        )
        with correlated(correlation_id), self.adopt(context):
            yield context

    @contextmanager
    def adopt(self, context: SpanContext | None) -> Iterator[None]:
        """Continue the trace ``context`` names, for the duration of the block.

        ``None`` is the sub-agent that was handed nothing. It starts its own
        trace rather than raising, because a lost thread is a degraded trace and
        a raise is a failed investigation.
        """
        previous = self._adopted
        self._adopted = context
        try:
            yield
        finally:
            self._adopted = previous

    @contextmanager
    def span(self, name: str, kind: SpanKind, **attributes: str) -> Iterator[Span]:
        """Open one span, and close it however the block ends.

        An exception is recorded and re-raised. A pipeline stage records its
        exception and re-raises; a trace that swallowed it would be a trace
        claiming the work succeeded.
        """
        parent = self.current()
        sampled = parent.sampled if parent else self._samples()
        opened = Span(
            name=name,
            kind=kind,
            context=SpanContext(
                trace_id=parent.trace_id if parent else self._trace_id(),
                span_id=self._span_id(),
                correlation_id=parent.correlation_id if parent else "",
                sampled=sampled,
            ),
            parent_span_id=parent.span_id if parent else "",
            started_ns=int(self.clock()),
            attributes=dict(attributes),
        )
        self._stack.append(opened)
        try:
            yield opened
        except Exception as error:
            opened.status = SpanStatus.ERROR
            opened.error = f"{type(error).__name__}: {error}"
            raise
        finally:
            self._stack.pop()
            opened.ended_ns = int(self.clock())
            if self.config.enabled and opened.context.sampled:
                self.finished.append(opened)

    def flush(self) -> int:
        """Export every finished span as one document, and return 1 or 0.

        The buffer is cleared whether or not the collector answered, for the
        reason the export queue is bounded: an outage must not grow a buffer
        inside the process that is investigating an incident.
        """
        spans = self.finished
        if not spans:
            return 0
        self.finished = []
        document = {
            "resourceSpans": [
                {
                    "resource": {"attributes": _attributes(self.config.resource_attributes())},
                    "scopeSpans": [
                        {
                            "scope": {"name": INSTRUMENTATION_SCOPE},
                            "spans": [_encode(span) for span in spans],
                        }
                    ],
                }
            ]
        }
        return 1 if self.exporter.export(TelemetrySignal.TRACES, document) else 0

    def _samples(self) -> bool:
        """Return whether a new trace is one of the ones exported."""
        return self.config.samples(self._random.random())

    def _trace_id(self) -> str:
        """Return a new trace identifier at the width the protocol fixes."""
        return secrets.token_hex(TRACE_ID_HEX_DIGITS // 2)

    def _span_id(self) -> str:
        """Return a new span identifier at the width the protocol fixes."""
        return secrets.token_hex(SPAN_ID_HEX_DIGITS // 2)


def _is_hex(value: str, digits: int) -> bool:
    """Return whether ``value`` is exactly ``digits`` hexadecimal characters."""
    if len(value) != digits:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _attributes(pairs: Mapping[str, str]) -> list[dict[str, Any]]:
    """Return one OTLP attribute list."""
    return [{"key": key, "value": {"stringValue": value}} for key, value in pairs.items()]


def _encode(span: Span) -> dict[str, Any]:
    """Return one span in the shape OTLP defines."""
    attributes = dict(span.attributes)
    if span.context.correlation_id:
        attributes[LOG_CORRELATION_FIELD] = span.context.correlation_id
    attributes["ninjasre.boundary"] = span.kind.value
    if span.error:
        attributes["error"] = span.error

    return {
        "traceId": span.context.trace_id,
        "spanId": span.context.span_id,
        "parentSpanId": span.parent_span_id,
        "name": span.name,
        "kind": _OTLP_KIND_CLIENT if span.kind is SpanKind.EXTERNAL_CALL else _OTLP_KIND_INTERNAL,
        "startTimeUnixNano": span.started_ns,
        "endTimeUnixNano": span.ended_ns,
        "attributes": _attributes(attributes),
        "status": {"code": _STATUS_CODE[span.status.value]},
    }


__all__ = [
    "INSTRUMENTATION_SCOPE",
    "Span",
    "SpanContext",
    "SpanKind",
    "SpanStatus",
    "Tracer",
]
