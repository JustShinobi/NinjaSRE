"""Logging and telemetry configuration names, defaults, and bounds.

Structured logging is configured exactly once, in
``platform/observability/logging.py``. No module configures its own. These are
the knobs that configuration reads.

Telemetry is opt-in and points at a collector the operator names. Nothing here
phones home: the export target is unset by default, and unset means nothing
leaves the host. Every bound below exists because an unbounded one is how a
collector dies — a label whose value space is the set of pod names produces a
time series per pod, per restart, forever.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

NINJASRE_LOG_LEVEL_ENV: Final = "NINJASRE_LOG_LEVEL"
NINJASRE_LOG_FORMAT_ENV: Final = "NINJASRE_LOG_FORMAT"

DEFAULT_LOG_LEVEL: Final = "INFO"

LOG_LEVELS: Final[tuple[str, ...]] = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

#: One JSON object per line, for a log shipper.
LOG_FORMAT_JSON: Final = "json"

#: Aligned, coloured key-value pairs, for a human at a terminal.
LOG_FORMAT_CONSOLE: Final = "console"

LOG_FORMATS: Final[tuple[str, ...]] = (LOG_FORMAT_JSON, LOG_FORMAT_CONSOLE)

#: Chosen when the operator names no format. A terminal gets the console
#: renderer and anything else gets JSON, because a log that is being captured is
#: a log that will be parsed.
DEFAULT_LOG_FORMAT: Final = LOG_FORMAT_JSON

#: Timestamps are ISO-8601 in UTC. An incident is reconstructed from logs
#: written in several timezones, and local time makes that guesswork.
LOG_TIMESTAMP_FORMAT: Final = "iso"

#: Per-module levels, as ``module=LEVEL`` pairs. Re-read on demand rather than
#: at import, which is what makes turning one subsystem up not a restart.
NINJASRE_LOG_MODULE_LEVELS_ENV: Final = "NINJASRE_LOG_MODULE_LEVELS"

MODULE_LEVEL_SEPARATOR: Final = ","
MODULE_LEVEL_ASSIGNMENT: Final = "="

#: The keys every structured log line carries, whatever emitted it. A fixed set
#: is what makes a log queryable; a line that names its fields differently from
#: the line above it is prose with punctuation in it.
LOG_FIELDS: Final[tuple[str, ...]] = ("timestamp", "level", "logger", "event")

#: Where the conversation identifier is bound. One name, so a query for one
#: investigation is one predicate rather than a union over spellings.
LOG_CORRELATION_FIELD: Final = "correlation_id"

#: Recorded on a line the guardrail engine altered, so a redaction is visible as
#: a redaction rather than as text that happens to contain a placeholder.
LOG_GUARDRAIL_FIELD: Final = "guardrail_rules_fired"

#: A value longer than this is scanned in full and then truncated for emission.
#: A megabyte of vendor error text in a log line is a log pipeline outage.
MAX_LOG_VALUE_CHARS: Final[int] = 4_096


# --- Telemetry ---------------------------------------------------------------


class TelemetrySignal(StrEnum):
    """The three OTLP signals, and the path each one is posted to."""

    TRACES = "traces"
    METRICS = "metrics"
    LOGS = "logs"


#: OTLP over HTTP. The paths are fixed by the protocol, so a collector reachable
#: at the configured base URL is reachable for all three signals.
OTLP_SIGNAL_PATHS: Final[dict[str, str]] = {
    TelemetrySignal.TRACES.value: "/v1/traces",
    TelemetrySignal.METRICS.value: "/v1/metrics",
    TelemetrySignal.LOGS.value: "/v1/logs",
}

#: OTLP/JSON rather than OTLP/protobuf. Every collector accepts it, it needs no
#: dependency to encode, and a dependency the operator has to audit is the cost
#: this feature exists to avoid imposing.
OTLP_CONTENT_TYPE: Final = "application/json"

#: What the collector is told this deployment is called.
NINJASRE_TELEMETRY_SERVICE_NAME_ENV: Final = "NINJASRE_TELEMETRY_SERVICE_NAME"
DEFAULT_TELEMETRY_SERVICE_NAME: Final = "ninjasre"

#: The share of traces exported, between 0 and 1. Sampling is the knob an
#: operator reaches for when instrumentation shows up in latency, so it is a
#: setting rather than a constant.
NINJASRE_TELEMETRY_SAMPLE_RATIO_ENV: Final = "NINJASRE_TELEMETRY_SAMPLE_RATIO"
DEFAULT_TELEMETRY_SAMPLE_RATIO: Final[float] = 1.0

#: How long one export may block before it is abandoned. Short, because an
#: investigation must not wait on a collector: a slow collector and a dead one
#: have to cost the same, which is nothing.
TELEMETRY_EXPORT_TIMEOUT_SECONDS: Final[float] = 5.0

#: How many records may wait for export before the oldest are dropped. Bounded,
#: because the alternative to dropping telemetry during a collector outage is
#: growing a queue inside the process that is investigating an incident.
MAX_TELEMETRY_QUEUE_DEPTH: Final[int] = 2_048

#: Distinct values one label may take before further ones collapse into the
#: overflow value. Two hundred is more teams, models, or capabilities than any
#: deployment has, and far fewer than one unbounded field produces in an hour.
MAX_METRIC_LABEL_VALUES: Final[int] = 200

#: Where a label's values go once it has spent its budget. A named bucket rather
#: than a dropped point, so the total still adds up and the overflow is visible.
METRIC_LABEL_OVERFLOW: Final = "__overflow__"

#: A label value longer than this is truncated. A label is a dimension, not a
#: payload, and a collector charges for every byte of both.
MAX_METRIC_LABEL_VALUE_CHARS: Final[int] = 120

#: Trace and span identifiers are hex, at the widths W3C trace-context fixes.
TRACE_ID_HEX_DIGITS: Final[int] = 32
SPAN_ID_HEX_DIGITS: Final[int] = 16

#: The W3C trace-context header, and the header the correlation identifier
#: travels in when the protocol allows one. The second is ours because trace
#: context carries no room for a name a person recognises.
TRACEPARENT_HEADER: Final = "traceparent"
CORRELATION_HEADER: Final = "X-NinjaSRE-Correlation-Id"
TRACEPARENT_VERSION: Final = "00"
TRACE_FLAG_SAMPLED: Final = "01"
TRACE_FLAG_NOT_SAMPLED: Final = "00"


__all__ = [
    "CORRELATION_HEADER",
    "DEFAULT_LOG_FORMAT",
    "DEFAULT_LOG_LEVEL",
    "DEFAULT_TELEMETRY_SAMPLE_RATIO",
    "DEFAULT_TELEMETRY_SERVICE_NAME",
    "LOG_CORRELATION_FIELD",
    "LOG_FIELDS",
    "LOG_FORMATS",
    "LOG_FORMAT_CONSOLE",
    "LOG_FORMAT_JSON",
    "LOG_GUARDRAIL_FIELD",
    "LOG_LEVELS",
    "LOG_TIMESTAMP_FORMAT",
    "MAX_LOG_VALUE_CHARS",
    "MAX_METRIC_LABEL_VALUES",
    "MAX_METRIC_LABEL_VALUE_CHARS",
    "MAX_TELEMETRY_QUEUE_DEPTH",
    "METRIC_LABEL_OVERFLOW",
    "MODULE_LEVEL_ASSIGNMENT",
    "MODULE_LEVEL_SEPARATOR",
    "NINJASRE_LOG_FORMAT_ENV",
    "NINJASRE_LOG_LEVEL_ENV",
    "NINJASRE_LOG_MODULE_LEVELS_ENV",
    "NINJASRE_TELEMETRY_SAMPLE_RATIO_ENV",
    "NINJASRE_TELEMETRY_SERVICE_NAME_ENV",
    "OTLP_CONTENT_TYPE",
    "OTLP_SIGNAL_PATHS",
    "SPAN_ID_HEX_DIGITS",
    "TELEMETRY_EXPORT_TIMEOUT_SECONDS",
    "TRACEPARENT_HEADER",
    "TRACEPARENT_VERSION",
    "TRACE_FLAG_NOT_SAMPLED",
    "TRACE_FLAG_SAMPLED",
    "TRACE_ID_HEX_DIGITS",
    "TelemetrySignal",
]
