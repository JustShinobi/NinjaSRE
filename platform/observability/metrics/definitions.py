"""The nine metric families, their instruments, and the labels each may carry.

This module is the whole answer to "what can an operator see". It is a
declaration rather than a set of call sites because the label set is the part
that has to be reviewed: adding a keyword argument at a call site is a one-word
change, and adding a dimension to a declaration here is visible as one.

Three instrument kinds, which is all OTLP needs and all a dashboard uses:

- a **counter** only goes up — invocations, failures, tokens, dollars;
- a **gauge** is whatever it is right now — queue depth, pending approvals;
- a **histogram** is a distribution — durations and latencies, where the median
  and the tail are different facts and an average hides both.

Aggregation is cumulative. A collector restart therefore loses nothing it cannot
recompute, and a process restart is visible as a reset rather than as a spike.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final, TypeVar

from config.constants.observability import TelemetrySignal
from platform.observability.config import TelemetryConfig
from platform.observability.export import OtlpExporter
from platform.observability.metrics.cardinality import (
    BoundLabels,
    CardinalityGuard,
    LabelSet,
)

#: The scope every instrument here belongs to, as the collector sees it.
INSTRUMENTATION_SCOPE: Final = "ninjasre"

#: Cumulative, in OTLP's enumeration. Delta temporality would make a dropped
#: export a permanently wrong total rather than one missing sample.
_AGGREGATION_CUMULATIVE: Final[int] = 2

#: Duration buckets, in seconds, from a fast tool call to an investigation that
#: ran to its ceiling. Chosen so the interesting region — a few seconds to a few
#: minutes — has resolution, rather than being one bucket at each end.
DURATION_BUCKETS: Final[tuple[float, ...]] = (
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
    60.0,
    120.0,
    300.0,
    600.0,
)


class MetricFamily(StrEnum):
    """The nine things an operator is promised visibility into."""

    INVESTIGATION = "investigation"
    COST = "cost"
    CAPABILITY = "capability"
    INTEGRATION = "integration"
    SCHEDULER = "scheduler"
    APPROVAL = "approval"
    GUARDRAIL = "guardrail"
    MEMORY = "memory"
    #: What the *model* costs in attempts, as opposed to what the endpoint costs
    #: in money. Every other family describes the platform; this one describes
    #: the weights behind it, which is the thing an operator running their own
    #: hardware can actually change.
    MODEL = "model"


class InstrumentKind(StrEnum):
    """What shape one instrument's data has."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    """One instrument: what it measures, in what unit, along which dimensions."""

    name: str
    family: MetricFamily
    kind: InstrumentKind
    unit: str
    description: str
    labels: LabelSet = field(default_factory=LabelSet)


_TEAM_TRIGGER_OUTCOME = LabelSet(("team", "trigger", "outcome"))
_TEAM_MODEL_PROVIDER = LabelSet(("team", "model", "provider"))
_CAPABILITY = LabelSet(("capability", "outcome_class"))
_INTEGRATION = LabelSet(("integration", "status"))
_APPROVAL = LabelSet(("team", "side_effect_level"))
_GUARDRAIL = LabelSet(("rule", "action"))
_TEAM = LabelSet(("team",))
_MODEL = LabelSet(("model", "provider"))
_MODEL_KIND = LabelSet(("model", "provider", "kind"))


DEFINITIONS: Final[tuple[MetricDefinition, ...]] = (
    # -- investigation ---------------------------------------------------------
    MetricDefinition(
        name="investigation.count",
        family=MetricFamily.INVESTIGATION,
        kind=InstrumentKind.COUNTER,
        unit="1",
        description="Investigations started, by team, trigger, and how they ended.",
        labels=_TEAM_TRIGGER_OUTCOME,
    ),
    MetricDefinition(
        name="investigation.duration",
        family=MetricFamily.INVESTIGATION,
        kind=InstrumentKind.HISTOGRAM,
        unit="s",
        description="Wall-clock seconds from an investigation starting to its answer.",
        labels=_TEAM_TRIGGER_OUTCOME,
    ),
    MetricDefinition(
        name="investigation.outcome",
        family=MetricFamily.INVESTIGATION,
        kind=InstrumentKind.COUNTER,
        unit="1",
        description="How investigations ended, so the distribution is readable on its own.",
        labels=_TEAM_TRIGGER_OUTCOME,
    ),
    # -- cost ------------------------------------------------------------------
    MetricDefinition(
        name="llm.input_tokens",
        family=MetricFamily.COST,
        kind=InstrumentKind.COUNTER,
        unit="1",
        description="Uncached prompt tokens, by team, model, and provider.",
        labels=_TEAM_MODEL_PROVIDER,
    ),
    MetricDefinition(
        name="llm.output_tokens",
        family=MetricFamily.COST,
        kind=InstrumentKind.COUNTER,
        unit="1",
        description="Completion tokens, by team, model, and provider.",
        labels=_TEAM_MODEL_PROVIDER,
    ),
    MetricDefinition(
        name="llm.cached_tokens",
        family=MetricFamily.COST,
        kind=InstrumentKind.COUNTER,
        unit="1",
        description="Prompt tokens served from a provider cache, counted separately "
        "because they are priced differently.",
        labels=_TEAM_MODEL_PROVIDER,
    ),
    MetricDefinition(
        name="llm.cost_usd",
        family=MetricFamily.COST,
        kind=InstrumentKind.COUNTER,
        unit="USD",
        description="Money spent on calls that could be priced, by team, model, and provider.",
        labels=_TEAM_MODEL_PROVIDER,
    ),
    MetricDefinition(
        name="llm.unpriced_calls",
        family=MetricFamily.COST,
        kind=InstrumentKind.COUNTER,
        unit="1",
        description="Calls with no published price, so a spend total is never read as complete.",
        labels=_TEAM_MODEL_PROVIDER,
    ),
    # -- capability ------------------------------------------------------------
    MetricDefinition(
        name="capability.invocations",
        family=MetricFamily.CAPABILITY,
        kind=InstrumentKind.COUNTER,
        unit="1",
        description="Capability calls, by capability and outcome class.",
        labels=_CAPABILITY,
    ),
    MetricDefinition(
        name="capability.failures",
        family=MetricFamily.CAPABILITY,
        kind=InstrumentKind.COUNTER,
        unit="1",
        description="Capability calls that failed, by capability and outcome class.",
        labels=_CAPABILITY,
    ),
    MetricDefinition(
        name="capability.duration",
        family=MetricFamily.CAPABILITY,
        kind=InstrumentKind.HISTOGRAM,
        unit="s",
        description="Seconds one capability call took, including the vendor's latency.",
        labels=_CAPABILITY,
    ),
    # -- integration -----------------------------------------------------------
    MetricDefinition(
        name="integration.health",
        family=MetricFamily.INTEGRATION,
        kind=InstrumentKind.GAUGE,
        unit="1",
        description="Whether one integration is currently usable, as 1 or 0.",
        labels=_INTEGRATION,
    ),
    MetricDefinition(
        name="integration.verifications",
        family=MetricFamily.INTEGRATION,
        kind=InstrumentKind.COUNTER,
        unit="1",
        description="Credential verifications run, by integration and result.",
        labels=_INTEGRATION,
    ),
    # -- scheduler -------------------------------------------------------------
    MetricDefinition(
        name="scheduler.queue_depth",
        family=MetricFamily.SCHEDULER,
        kind=InstrumentKind.GAUGE,
        unit="1",
        description="Jobs waiting to be claimed across the whole deployment.",
    ),
    MetricDefinition(
        name="scheduler.claim_latency",
        family=MetricFamily.SCHEDULER,
        kind=InstrumentKind.HISTOGRAM,
        unit="s",
        description="Seconds between a job becoming due and a worker claiming it.",
    ),
    MetricDefinition(
        name="scheduler.misfires",
        family=MetricFamily.SCHEDULER,
        kind=InstrumentKind.COUNTER,
        unit="1",
        description="Jobs whose due time passed without a worker claiming them.",
    ),
    # -- approval --------------------------------------------------------------
    MetricDefinition(
        name="approval.pending",
        family=MetricFamily.APPROVAL,
        kind=InstrumentKind.GAUGE,
        unit="1",
        description="Requests waiting on a person, by team and side-effect level.",
        labels=_APPROVAL,
    ),
    MetricDefinition(
        name="approval.decision_latency",
        family=MetricFamily.APPROVAL,
        kind=InstrumentKind.HISTOGRAM,
        unit="s",
        description="Seconds a request waited for a decision — the cost of gating, measured.",
        labels=_APPROVAL,
    ),
    MetricDefinition(
        name="approval.outcome",
        family=MetricFamily.APPROVAL,
        kind=InstrumentKind.COUNTER,
        unit="1",
        description="Decisions taken, by team and side-effect level.",
        labels=_APPROVAL,
    ),
    # -- guardrail -------------------------------------------------------------
    MetricDefinition(
        name="guardrail.actions",
        family=MetricFamily.GUARDRAIL,
        kind=InstrumentKind.COUNTER,
        unit="1",
        description="Guardrail matches, by rule and the action the match caused.",
        labels=_GUARDRAIL,
    ),
    # -- memory ----------------------------------------------------------------
    MetricDefinition(
        name="memory.recalls",
        family=MetricFamily.MEMORY,
        kind=InstrumentKind.COUNTER,
        unit="1",
        description="Episodic recalls attempted, by team.",
        labels=_TEAM,
    ),
    MetricDefinition(
        name="memory.recall_hits",
        family=MetricFamily.MEMORY,
        kind=InstrumentKind.COUNTER,
        unit="1",
        description="Recalls that returned an episode, by team — the hit rate's numerator.",
        labels=_TEAM,
    ),
    MetricDefinition(
        name="memory.episodes_written",
        family=MetricFamily.MEMORY,
        kind=InstrumentKind.COUNTER,
        unit="1",
        description="Episodes written at the end of an investigation, by team.",
        labels=_TEAM,
    ),
    # -- model behaviour --------------------------------------------------------
    MetricDefinition(
        name="model.repairs",
        family=MetricFamily.MODEL,
        kind=InstrumentKind.COUNTER,
        unit="1",
        description="Model output the system had to repair before it could be used, "
        "by model, provider, and what was wrong with it.",
        labels=_MODEL_KIND,
    ),
    MetricDefinition(
        name="model.degradations",
        family=MetricFamily.MODEL,
        kind=InstrumentKind.COUNTER,
        unit="1",
        description="Runs that degraded because of the model rather than the endpoint, "
        "by model, provider, and cause.",
        labels=_MODEL_KIND,
    ),
    MetricDefinition(
        name="model.loop_breaks",
        family=MetricFamily.MODEL,
        kind=InstrumentKind.COUNTER,
        unit="1",
        description="Times a model was stopped repeating one call, by model and provider.",
        labels=_MODEL,
    ),
    MetricDefinition(
        name="model.compactions",
        family=MetricFamily.MODEL,
        kind=InstrumentKind.COUNTER,
        unit="1",
        description="Transcripts summarised to stay inside the model's usable context, "
        "by model and provider.",
        labels=_MODEL,
    ),
    MetricDefinition(
        name="model.truncations",
        family=MetricFamily.MODEL,
        kind=InstrumentKind.COUNTER,
        unit="1",
        description="Capability results shortened before the model read them, "
        "by model and provider.",
        labels=_MODEL,
    ),
)

_BY_NAME: Final[dict[str, MetricDefinition]] = {
    definition.name: definition for definition in DEFINITIONS
}


def definition_for(name: str) -> MetricDefinition:
    """Return the declaration for ``name``.

    Raises:
        KeyError: no instrument by that name is declared. Undeclared instruments
            are refused rather than created on demand, because a metric nobody
            declared is a metric nobody reviewed the labels of.
    """
    try:
        return _BY_NAME[name]
    except KeyError:
        raise KeyError(
            f"{name!r} is not a declared instrument; add it to "
            f"platform/observability/metrics/definitions.py with its label set"
        ) from None


@dataclass(slots=True)
class _Instrument:
    """What every instrument shares: its declaration and how it binds labels."""

    definition: MetricDefinition
    guard: CardinalityGuard

    def key(self, labels: Mapping[str, str]) -> BoundLabels:
        """Return the bounded, sorted series key ``labels`` names."""
        bound = self.definition.labels.bind(labels)
        return tuple(
            (name, self.guard.bound(self.definition.name, name, value)) for name, value in bound
        )


@dataclass(slots=True)
class Counter(_Instrument):
    """A quantity that only goes up."""

    points: dict[BoundLabels, float] = field(default_factory=dict)

    def add(self, amount: float, **labels: str) -> None:
        """Add ``amount`` to the series ``labels`` names."""
        key = self.key(labels)
        self.points[key] = self.points.get(key, 0.0) + amount

    def value(self, **labels: str) -> float:
        """Return the running total for one series."""
        return self.points.get(self.key(labels), 0.0)


@dataclass(slots=True)
class Gauge(_Instrument):
    """A quantity that is whatever it currently is."""

    points: dict[BoundLabels, float] = field(default_factory=dict)

    def set(self, amount: float, **labels: str) -> None:
        """Replace the current value of the series ``labels`` names."""
        self.points[self.key(labels)] = amount

    def value(self, **labels: str) -> float:
        """Return the current value for one series."""
        return self.points.get(self.key(labels), 0.0)


@dataclass(slots=True)
class _Distribution:
    """One series of a histogram: its count, its sum, and its buckets."""

    count: int = 0
    total: float = 0.0
    buckets: list[int] = field(default_factory=lambda: [0] * (len(DURATION_BUCKETS) + 1))


@dataclass(slots=True)
class Histogram(_Instrument):
    """A distribution, kept as buckets so the tail survives aggregation."""

    points: dict[BoundLabels, _Distribution] = field(default_factory=dict)

    def record(self, amount: float, **labels: str) -> None:
        """Record one observation into the series ``labels`` names."""
        distribution = self.points.setdefault(self.key(labels), _Distribution())
        distribution.count += 1
        distribution.total += amount
        distribution.buckets[_bucket_index(amount)] += 1

    def count(self, **labels: str) -> int:
        """Return how many observations one series holds."""
        found = self.points.get(self.key(labels))
        return found.count if found else 0

    def total(self, **labels: str) -> float:
        """Return the sum of one series' observations."""
        found = self.points.get(self.key(labels))
        return found.total if found else 0.0


def _bucket_index(amount: float) -> int:
    """Return which bucket ``amount`` falls into, the last one being the overflow."""
    for index, bound in enumerate(DURATION_BUCKETS):
        if amount <= bound:
            return index
    return len(DURATION_BUCKETS)


Instrument = Counter | Gauge | Histogram

#: Which of the three an accessor is asking for, so ``counter`` returns a
#: ``Counter`` rather than "one of the three" and a caller keeps its types.
_Kind = TypeVar("_Kind", Counter, Gauge, Histogram)


@dataclass(slots=True)
class MetricRegistry:
    """Every instrument this process writes, and the one place they are exported.

    A disabled deployment creates instruments that accept writes and keep
    nothing. That is deliberate: the alternative is a branch at every call site
    asking whether telemetry is on, and a call site with a branch on it is a
    call site somebody forgets to add the branch to.
    """

    config: TelemetryConfig
    exporter: OtlpExporter
    guard: CardinalityGuard = field(default_factory=CardinalityGuard)
    clock: Any = field(default=time.time_ns)
    _instruments: dict[str, Instrument] = field(default_factory=dict, repr=False)

    def counter(self, name: str) -> Counter:
        """Return the declared counter called ``name``."""
        return self._instrument(name, InstrumentKind.COUNTER, Counter)

    def gauge(self, name: str) -> Gauge:
        """Return the declared gauge called ``name``."""
        return self._instrument(name, InstrumentKind.GAUGE, Gauge)

    def histogram(self, name: str) -> Histogram:
        """Return the declared histogram called ``name``."""
        return self._instrument(name, InstrumentKind.HISTOGRAM, Histogram)

    def snapshot(self) -> list[dict[str, Any]]:
        """Return every instrument's current points, in OTLP metric shape."""
        if not self.config.enabled:
            return []
        moment = int(self.clock())
        return [
            _encode(instrument, moment)
            for instrument in self._instruments.values()
            if _has_points(instrument)
        ]

    def flush(self) -> int:
        """Export one OTLP document holding every metric, and return 1 or 0.

        One document rather than one per instrument: a collector charges per
        request, and an investigation that produced twenty instruments should
        not produce twenty POSTs.
        """
        metrics = self.snapshot()
        if not metrics:
            return 0
        document = {
            "resourceMetrics": [
                {
                    "resource": {"attributes": _attributes(self.config.resource_attributes())},
                    "scopeMetrics": [
                        {"scope": {"name": INSTRUMENTATION_SCOPE}, "metrics": metrics}
                    ],
                }
            ]
        }
        return 1 if self.exporter.export(TelemetrySignal.METRICS, document) else 0

    def _instrument(
        self,
        name: str,
        kind: InstrumentKind,
        cls: type[_Kind],
    ) -> _Kind:
        """Return the instrument called ``name``, creating it on first use.

        Raises:
            KeyError: ``name`` is not declared.
            TypeError: ``name`` is declared as a different kind. Returning the
                wrong kind would silently turn a distribution into a total.
        """
        definition = definition_for(name)
        if definition.kind is not kind:
            raise TypeError(
                f"{name!r} is declared as a {definition.kind.value}, not a {kind.value}"
            )
        existing = self._instruments.get(name)
        if not isinstance(existing, cls):
            existing = cls(definition=definition, guard=self.guard)
            self._instruments[name] = existing
        return existing


def _has_points(instrument: Instrument) -> bool:
    """Return whether an instrument has anything to export."""
    return bool(instrument.points)


def _attributes(labels: Mapping[str, str] | BoundLabels) -> list[dict[str, Any]]:
    """Return one OTLP attribute list, whichever shape the labels arrived in."""
    pairs = labels.items() if isinstance(labels, Mapping) else labels
    return [{"key": key, "value": {"stringValue": value}} for key, value in pairs]


def _encode(instrument: Instrument, moment: int) -> dict[str, Any]:
    """Return one instrument as the OTLP metric its kind defines."""
    definition = instrument.definition
    head: dict[str, Any] = {
        "name": definition.name,
        "unit": definition.unit,
        "description": definition.description,
    }

    if isinstance(instrument, Histogram):
        head["histogram"] = {
            "aggregationTemporality": _AGGREGATION_CUMULATIVE,
            "dataPoints": [
                {
                    "attributes": _attributes(key),
                    "timeUnixNano": moment,
                    "count": distribution.count,
                    "sum": distribution.total,
                    "bucketCounts": list(distribution.buckets),
                    "explicitBounds": list(DURATION_BUCKETS),
                }
                for key, distribution in sorted(instrument.points.items())
            ],
        }
        return head

    points = [
        {"attributes": _attributes(key), "timeUnixNano": moment, "asDouble": float(value)}
        for key, value in sorted(instrument.points.items())
    ]
    if isinstance(instrument, Gauge):
        head["gauge"] = {"dataPoints": points}
    else:
        head["sum"] = {
            "aggregationTemporality": _AGGREGATION_CUMULATIVE,
            "isMonotonic": True,
            "dataPoints": points,
        }
    return head


__all__ = [
    "DEFINITIONS",
    "DURATION_BUCKETS",
    "INSTRUMENTATION_SCOPE",
    "Counter",
    "Gauge",
    "Histogram",
    "Instrument",
    "InstrumentKind",
    "MetricDefinition",
    "MetricFamily",
    "MetricRegistry",
    "definition_for",
]
