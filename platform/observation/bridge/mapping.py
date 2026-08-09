"""Deciding which resource a metric series is about, from its labels alone.

This is the join the whole feature exists to make, and it is the part that is
genuinely deployment-specific — except for the exporters everybody runs, whose
label schemes are stable enough to ship. So: declared rules, shipped defaults,
and everything else configured.

**A rule is a template over labels, not an expression.** ``lxc/*/*/{id:-1}``
says: take the last segment of the ``id`` label, and find the estate resource
whose native identity is a container with that VMID, in any cluster, created at
any time. There is no arithmetic, no conditional and no function call, for the
same reason a detector has four condition kinds — a mapping language would be a
second programming language nobody can validate.

**Nothing here creates a resource.** A rule resolves to a *pattern*, and the
pattern is matched against the estate as it stands. A series naming a guest the
estate does not hold is reported as unmapped, which is the honest answer: the
metrics system and the estate disagree, and one of them is out of date. Writing
the resource would make the estate agree with whichever was wrong.

**A destroyed guest keeps its history.** Proxmox writes the creation time into a
guest's identity precisely so that VMID 100 and the VMID 100 before it are
different resources — and metrics outlive guests, so a series about a destroyed
container matches the absent resource it was always about. When a VMID has been
reused and both are in the estate the live one wins, and when two live resources
match the mapping is reported as ambiguous rather than guessed. A silent wrong
join is worse than a visible gap, because the wrong join produces a detector
firing about the wrong guest.

**Unmapped is reported, with labels.** A silent mapping gap is a metric the
operator believes is being watched and is not. Reporting the labels turns
configuring the bridge into an iterative, visible task, and the bound on the
report is stated rather than applied quietly.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final

from config.constants.observability_bridge import (
    DEFAULT_MAPPING_INTERVAL_SECONDS,
    MAX_MAPPED_SERIES,
    MAX_UNMAPPED_REPORTED,
    MIN_MAPPING_INTERVAL_SECONDS,
)
from platform.observation.bridge.errors import BridgeBoundExceeded
from platform.observation.bridge.ports import MetricSeries
from platform.persistence.ports.estate_repository import Resource


class SeriesView(StrEnum):
    """Whose account of a resource a series is.

    The distinction matters most for a guest. A hypervisor reporting a container
    at 12% CPU and the container's own exporter reporting 60% are not in
    disagreement — they are measuring different denominators — and an
    investigation that could not tell them apart would present one as
    contradicting the other.
    """

    #: The cluster's account of one of its own resources.
    HYPERVISOR = "hypervisor"
    #: A machine's account of itself, from an exporter running on it.
    NODE = "node"
    #: A guest's account of itself, from an exporter running inside it.
    GUEST = "guest"


#: ``{label}``, ``{label:host}``, or ``{label:<index>}``. Three forms and no
#: fourth: ``host`` takes what comes before the first colon, so a scrape target
#: of ``pve01:9100`` yields ``pve01``, and an index takes one ``/``-separated
#: segment, negative counting from the end. Anything a rule cannot say in those
#: terms is a rule that wanted an expression, and a mapping expression is the
#: second query language this package refuses to have.
_PLACEHOLDER: Final = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)(?::(host|-?\d+))?\}")

#: What a template segment says when it does not care. It matches exactly one
#: segment of a native identity — never several — because a wildcard that
#: swallowed segments would make ``node/*`` match a guest.
WILDCARD: Final = "*"


@dataclass(frozen=True, slots=True)
class LabelRule:
    """One declared association between a family of series and a kind of resource.

    ``native_template`` addresses the *estate's* native identity rather than its
    hashed resource id, because a label set can reconstruct "container 100" and
    can never reconstruct a digest. The parts a metrics system cannot know — a
    guest's creation time, usually the cluster name — are wildcards, and a
    deployment where a wildcard is ambiguous says so by declaring the label.
    """

    rule_id: str
    #: Metric-name prefixes this rule claims. A prefix rather than a list of
    #: names: an exporter publishes dozens of series about one thing and naming
    #: each would be a rule that goes stale on the exporter's next release.
    metric_prefixes: tuple[str, ...]
    resource_kind: str
    #: The estate source whose native identities the template addresses.
    integration: str
    native_template: str
    #: Labels that must *start with* these values for the rule to claim a series.
    #: This is how one exporter's series are split by what they are about —
    #: ``prometheus-pve-exporter`` says ``id="lxc/100"`` and ``id="node/pve01"``
    #: on otherwise identical metrics.
    when_labels: Mapping[str, str] = field(default_factory=dict)
    view: SeriesView = SeriesView.HYPERVISOR
    description: str = ""

    def __post_init__(self) -> None:
        if not self.rule_id:
            raise ValueError("A label rule needs an identifier; it appears in every report.")
        if not self.metric_prefixes:
            raise ValueError(
                f"label rule {self.rule_id!r} claims no metrics. A rule that claims nothing "
                f"is a rule nobody will notice is not working."
            )
        if not self.native_template:
            raise ValueError(f"label rule {self.rule_id!r} resolves to no identity.")

    @property
    def required_labels(self) -> tuple[str, ...]:
        """Return the labels a series must carry for this rule to resolve.

        Derived from the template rather than declared beside it, so the two
        cannot disagree — and so a rule that gained a placeholder cannot keep
        matching series that no longer have what it needs.
        """
        seen: list[str] = []
        for match in _PLACEHOLDER.finditer(self.native_template):
            if match.group(1) not in seen:
                seen.append(match.group(1))
        return tuple(seen)

    def applies_to_labels(self, labels: Mapping[str, str]) -> bool:
        """Return whether ``labels`` satisfy this rule's conditions.

        The metric name is deliberately not consulted. An Alertmanager alert has
        labels and no metric name, and correlating one to a resource is the same
        question this rule already answers — so it is answered by the same rule
        rather than by a second, parallel set an operator has to keep in step.
        """
        return all(
            labels.get(label, "").startswith(value) for label, value in self.when_labels.items()
        )

    def claims(self, series: MetricSeries) -> bool:
        """Return whether this rule is the one that should resolve ``series``."""
        if not any(series.metric.startswith(prefix) for prefix in self.metric_prefixes):
            return False
        return self.applies_to_labels(series.labels)

    def missing_labels(self, series: MetricSeries) -> tuple[str, ...]:
        """Return the labels this rule needs and ``series`` does not carry."""
        return self.missing_labels_in(series.labels)

    def missing_labels_in(self, labels: Mapping[str, str]) -> tuple[str, ...]:
        """Return the labels this rule needs and ``labels`` does not carry."""
        return tuple(label for label in self.required_labels if not labels.get(label))

    def pattern_for(self, series: MetricSeries) -> str:
        """Return the native-identity pattern ``series`` resolves to under this rule."""
        return self.pattern_for_labels(series.labels)

    def pattern_for_labels(self, labels: Mapping[str, str]) -> str:
        """Return the native-identity pattern ``labels`` resolve to under this rule.

        Returns the empty string when a required label is absent, which the
        caller turns into a reason. Substituting an empty segment instead would
        produce a pattern that matches something, and matching the wrong thing
        is the failure this whole module is arranged to avoid.
        """
        if self.missing_labels_in(labels):
            return ""

        def substitute(match: re.Match[str]) -> str:
            return _extract(labels.get(match.group(1), ""), match.group(2))

        resolved = _PLACEHOLDER.sub(substitute, self.native_template)
        return "" if any(part == "" for part in resolved.split("/")) else resolved


def _extract(value: str, modifier: str | None) -> str:
    """Return the part of ``value`` a placeholder's modifier names."""
    if modifier is None:
        return value
    if modifier == "host":
        return value.split(":", 1)[0]
    segments = value.split("/")
    index = int(modifier)
    if -len(segments) <= index < len(segments):
        return segments[index]
    return ""


@dataclass(frozen=True, slots=True)
class MappedSeries:
    """One series and the estate resource it describes."""

    series: MetricSeries
    resource_id: str
    resource_kind: str
    rule_id: str
    view: SeriesView

    @property
    def metric(self) -> str:
        """Return the metric name."""
        return self.series.metric

    @property
    def labels(self) -> Mapping[str, str]:
        """Return the source's own label set."""
        return self.series.labels


@dataclass(frozen=True, slots=True)
class UnmappedSeries:
    """One series nothing could be said about, and why.

    The labels travel with it. "Some series are unmapped" is not actionable;
    ``mystery_metric_total{app="something"}`` is a rule somebody can write.
    """

    metric: str
    labels: Mapping[str, str]
    reason: str


@dataclass(frozen=True, slots=True)
class SeriesMapping:
    """What one mapping pass associated, what it could not, and what it did not reach."""

    mapped: tuple[MappedSeries, ...] = ()
    unmapped: tuple[UnmappedSeries, ...] = ()
    #: Every unmapped series encountered, including the ones past the report's
    #: bound. A sample without a total would understate a mapping gap.
    unmapped_total: int = 0
    considered: int = 0
    truncated: bool = False

    @property
    def resource_ids(self) -> set[str]:
        """Return the estate resources this pass associated series with."""
        return {entry.resource_id for entry in self.mapped}

    @property
    def summary(self) -> str:
        """Return the one line an operator reads about a mapping pass."""
        line = (
            f"{len(self.mapped)} of {self.considered} series mapped to "
            f"{len(self.resource_ids)} resources; {self.unmapped_total} unmapped"
        )
        if self.truncated:
            return f"{line}; stopped at {MAX_MAPPED_SERIES} series and did not reach the rest"
        return line


@dataclass(frozen=True, slots=True)
class EstateIndex:
    """The estate, arranged so a native-identity pattern can be resolved cheaply.

    Keyed on the last segment of the native identity — a VMID, a node name, a
    datastore name — because that is the discriminating part of every identity
    this package matches, and scanning the whole estate per series is the cost
    NFR-001 exists to bound.
    """

    by_tail: Mapping[tuple[str, str, str], tuple[Resource, ...]] = field(default_factory=dict)

    @classmethod
    def of(cls, resources: Iterable[Resource]) -> EstateIndex:
        """Return an index over ``resources``."""
        grouped: dict[tuple[str, str, str], list[Resource]] = {}
        for resource in resources:
            tail = resource.native_id.rsplit("/", 1)[-1]
            grouped.setdefault((resource.source, resource.kind, tail), []).append(resource)
        return cls(by_tail={key: tuple(value) for key, value in grouped.items()})

    def resolve(self, pattern: str, *, kind: str, integration: str) -> tuple[Resource, ...]:
        """Return every resource whose native identity matches ``pattern``."""
        segments = pattern.split("/")
        tail = segments[-1]
        if tail == WILDCARD:
            candidates = tuple(
                resource
                for (source, resource_kind, _), group in self.by_tail.items()
                if source == integration and resource_kind == kind
                for resource in group
            )
        else:
            candidates = self.by_tail.get((integration, kind, tail), ())
        return tuple(resource for resource in candidates if _matches(segments, resource.native_id))


def _matches(pattern: Sequence[str], native_id: str) -> bool:
    """Return whether ``native_id`` matches a segment pattern exactly."""
    segments = native_id.split("/")
    if len(segments) != len(pattern):
        return False
    return all(
        expected in (WILDCARD, found) for expected, found in zip(pattern, segments, strict=True)
    )


@dataclass(frozen=True, slots=True)
class MappingSchedule:
    """How often the join is rebuilt.

    On a schedule rather than per query. The join changes when the estate
    changes or when a scrape target is added — both minute-scale events — and
    rebuilding it inside a detector evaluation would multiply its cost by the
    detector count for information that has not changed.
    """

    interval_seconds: int = DEFAULT_MAPPING_INTERVAL_SECONDS

    def __post_init__(self) -> None:
        if self.interval_seconds < MIN_MAPPING_INTERVAL_SECONDS:
            raise BridgeBoundExceeded(
                parameter="mapping interval",
                requested=self.interval_seconds,
                limit=MIN_MAPPING_INTERVAL_SECONDS,
                constant="MIN_MAPPING_INTERVAL_SECONDS",
            )

    def is_due(self, *, last_mapped_at: datetime | None, now: datetime) -> bool:
        """Return whether the mapping should be rebuilt at ``now``."""
        if last_mapped_at is None:
            return True
        return now - last_mapped_at >= timedelta(seconds=self.interval_seconds)


def map_series(
    series: Iterable[MetricSeries],
    *,
    rules: Sequence[LabelRule],
    estate: EstateIndex,
) -> SeriesMapping:
    """Return which of ``series`` describe which estate resources, and what did not.

    Bounded at ``MAX_MAPPED_SERIES`` considered, and the bound is reported rather
    than applied silently — a pass that stopped early and said nothing would be a
    deployment believing it had mapped a metrics system it had only sampled.
    """
    mapped: list[MappedSeries] = []
    unmapped: list[UnmappedSeries] = []
    unmapped_total = 0
    considered = 0
    truncated = False

    for entry in series:
        if considered >= MAX_MAPPED_SERIES:
            truncated = True
            break
        considered += 1
        resolved = _resolve(entry, rules=rules, estate=estate)
        if isinstance(resolved, MappedSeries):
            mapped.append(resolved)
            continue
        unmapped_total += 1
        if len(unmapped) < MAX_UNMAPPED_REPORTED:
            unmapped.append(resolved)

    return SeriesMapping(
        mapped=tuple(mapped),
        unmapped=tuple(unmapped),
        unmapped_total=unmapped_total,
        considered=considered,
        truncated=truncated,
    )


def _resolve(
    entry: MetricSeries,
    *,
    rules: Sequence[LabelRule],
    estate: EstateIndex,
) -> MappedSeries | UnmappedSeries:
    """Return the resource ``entry`` describes, or the reason nothing could be said."""
    claimed = [rule for rule in rules if rule.claims(entry)]
    if not claimed:
        return UnmappedSeries(
            metric=entry.metric,
            labels=entry.labels,
            reason=(
                "no declared label rule claims this metric; declare one naming the "
                "resource kind its labels identify"
            ),
        )

    reasons: list[str] = []
    for rule in claimed:
        missing = rule.missing_labels(entry)
        if missing:
            reasons.append(f"rule {rule.rule_id!r} needs the label(s) {', '.join(missing)}")
            continue
        pattern = rule.pattern_for(entry)
        if not pattern:
            reasons.append(f"rule {rule.rule_id!r} resolved to an empty identity")
            continue
        candidates = estate.resolve(pattern, kind=rule.resource_kind, integration=rule.integration)
        if not candidates:
            reasons.append(
                f"rule {rule.rule_id!r} resolved to {pattern!r}, which the estate does "
                f"not hold; the metrics system and the estate disagree"
            )
            continue
        chosen = choose_resource(candidates)
        if chosen is None:
            names = ", ".join(sorted(resource.native_id for resource in candidates))
            reasons.append(
                f"rule {rule.rule_id!r} is ambiguous: {pattern!r} matches {names}. "
                f"Declare the label that tells them apart rather than picking one"
            )
            continue
        return MappedSeries(
            series=entry,
            resource_id=chosen.resource_id,
            resource_kind=chosen.kind,
            rule_id=rule.rule_id,
            view=rule.view,
        )

    return UnmappedSeries(metric=entry.metric, labels=entry.labels, reason="; ".join(reasons))


def choose_resource(candidates: tuple[Resource, ...]) -> Resource | None:
    """Return the one resource a pattern is about, or ``None`` when it is ambiguous.

    A single match is the answer whether or not it is absent: metrics outlive
    guests, and the series about a destroyed container belongs to the container
    that was destroyed. Where a VMID has been reused the live one wins, because
    what is publishing now is what is running now. Two live matches is a genuine
    ambiguity and is reported.
    """
    if len(candidates) == 1:
        return candidates[0]
    live = [resource for resource in candidates if resource.absent_since is None]
    return live[0] if len(live) == 1 else None


__all__ = [
    "WILDCARD",
    "EstateIndex",
    "LabelRule",
    "MappedSeries",
    "MappingSchedule",
    "SeriesMapping",
    "SeriesView",
    "UnmappedSeries",
    "choose_resource",
    "map_series",
]
