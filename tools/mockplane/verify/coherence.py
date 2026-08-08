"""Is this dataset a plausible history, does it keep its distribution, and is it awkward?

Three checks that a dataset can fail while validating perfectly against the
contract.

**Plausibility.** A run whose events are out of order, an incident that closed
before it opened, an episode created before the run that produced it. Each
renders without complaint and each teaches a reviewer something false about how
the product behaves.

**Distribution.** Anonymisation is allowed to change identity and nothing else.
The count of each resource kind, the ratio between them, the utilisation
percentages, the payload sizes and the skew between nodes are what the console
is being designed against — a pipeline that rounded a percentage while renaming
a host would produce a tidy dataset and destroy the reason for capturing a real
one.

**Awkwardness.** The properties nobody invents: a volume above its ceiling while
its datastore reads comfortable, a job that exists and is disabled, a set of
failed units, a datastore answering unknown, a guest covered by nothing. A
dataset without them lets a console pass review while being untested against
what it will actually meet.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from tools.mockplane.capture.projection import VOLUME_HIGH_PERCENT
from tools.mockplane.records import CapturedRecord


@dataclass(frozen=True, slots=True)
class Implausibility:
    """One way the dataset fails to read as something that happened."""

    slug: str
    pointer: str
    message: str

    def __str__(self) -> str:
        return f"{self.slug}{self.pointer}: {self.message}"


def _attributes(entry: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return one resource's attributes, or an empty mapping."""
    found = entry.get("attributes")
    return found if isinstance(found, dict) else {}


@dataclass(frozen=True, slots=True)
class Distribution:
    """The shape of a dataset, in the properties anonymisation must not touch."""

    resources_by_kind: Mapping[str, int] = field(default_factory=dict)
    resources_by_node: Mapping[str, int] = field(default_factory=dict)
    percentages: tuple[float, ...] = field(default_factory=tuple)
    #: One number per record: how many values its payload holds, at any depth. A
    #: proxy for payload size that does not move when a name gets longer.
    payload_sizes: Mapping[str, int] = field(default_factory=dict)
    states: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Awkwardness:
    """Which of the properties worth keeping actually survived."""

    volume_above_ceiling: bool = False
    disabled_backup_job: bool = False
    failed_units: bool = False
    unknown_datastore: bool = False
    uncovered_guest: bool = False

    @property
    def missing(self) -> tuple[str, ...]:
        """Return the awkward properties this dataset does not have."""
        return tuple(
            name
            for name, present in (
                ("a volume above its own ceiling", self.volume_above_ceiling),
                ("a backup job that exists and is disabled", self.disabled_backup_job),
                ("a node with failed units", self.failed_units),
                ("a datastore answering unknown", self.unknown_datastore),
                ("a guest covered by no enabled backup job", self.uncovered_guest),
            )
            if not present
        )

    def __bool__(self) -> bool:
        return not self.missing


def implausibilities(records: Sequence[CapturedRecord]) -> tuple[Implausibility, ...]:
    """Return every way the dataset fails to read as a coherent history."""
    found: list[Implausibility] = []
    started: dict[str, datetime] = {}

    for record in records:
        if record.slug == "runs":
            for index, run in enumerate(_rows(record.body, "runs")):
                identifier = str(run.get("run_id", ""))
                begun = _instant(run.get("started_at"))
                ended = _instant(run.get("completed_at") or run.get("finished_at"))
                if begun is not None:
                    started[identifier] = begun
                if begun is not None and ended is not None and ended < begun:
                    found.append(
                        Implausibility("runs", f"/runs/{index}", "it completed before it started")
                    )
        elif record.slug in {"run-replay", "run-threads"}:
            found.extend(_ordered(record))
        elif record.slug == "incidents":
            for index, incident in enumerate(_rows(record.body, "incidents")):
                opened = _instant(incident.get("opened_at"))
                closed = _instant(incident.get("closed_at"))
                if opened is not None and closed is not None and closed < opened:
                    found.append(
                        Implausibility(
                            "incidents", f"/incidents/{index}", "it closed before it opened"
                        )
                    )
                if incident.get("state") == "closed" and closed is None:
                    found.append(
                        Implausibility(
                            "incidents",
                            f"/incidents/{index}",
                            "it is closed and has no closing time",
                        )
                    )

    for record in records:
        if record.slug != "episodes":
            continue
        for index, episode in enumerate(_rows(record.body, "episodes")):
            produced_by = str(episode.get("run_id", ""))
            created = _instant(episode.get("created_at") or episode.get("occurred_at"))
            begun = started.get(produced_by)
            if created is not None and begun is not None and created < begun:
                found.append(
                    Implausibility(
                        "episodes",
                        f"/episodes/{index}",
                        f"it was created before run {produced_by!r} started",
                    )
                )
    return tuple(found)


def distribution_of(records: Sequence[CapturedRecord]) -> Distribution:
    """Return the shape of ``records``, in the properties anonymisation must preserve."""
    by_kind: dict[str, int] = {}
    by_node: dict[str, int] = {}
    states: dict[str, int] = {}
    percentages: list[float] = []
    sizes: dict[str, int] = {}

    for record in records:
        sizes[f"{record.slug}:{_arguments_key(record)}"] = _leaves(record.body)
        percentages.extend(_percentages(record.body))
        if record.slug != "estate-resources":
            continue
        for resource in _rows(record.body, "resources"):
            kind = str(resource.get("kind", ""))
            # The estate endpoint's own names. ``parent_name`` is the node a
            # guest runs on and ``health`` is the derived verdict; the shape
            # this used to read was the projection's, and the projection is
            # gone now that the endpoint is served.
            node = str(resource.get("parent_name", ""))
            state = str(resource.get("health", ""))
            by_kind[kind] = by_kind.get(kind, 0) + 1
            by_node[node] = by_node.get(node, 0) + 1
            states[state] = states.get(state, 0) + 1

    return Distribution(
        resources_by_kind=by_kind,
        resources_by_node=by_node,
        percentages=tuple(sorted(percentages)),
        payload_sizes=sizes,
        states=states,
    )


def awkwardness_of(records: Sequence[CapturedRecord]) -> Awkwardness:
    """Return which awkward properties survived into ``records``."""
    volume = False
    disabled = False
    units = False
    unknown = False
    uncovered = False

    for record in records:
        if record.slug == "estate-storage":
            volume = volume or any(
                _number(entry.get("used_percent")) >= VOLUME_HIGH_PERCENT
                for entry in _rows(record.body, "volumes")
            )
            unknown = unknown or any(
                entry.get("status") == "unknown" for entry in _rows(record.body, "datastores")
            )
        elif record.slug == "estate-backups":
            for job in _rows(record.body, "jobs"):
                disabled = disabled or job.get("enabled") is False
                uncovered = uncovered or _number(job.get("uncovered")) > 0
        elif record.slug == "estate-nodes":
            units = units or any(
                bool(node.get("failed_units")) for node in _rows(record.body, "nodes")
            )
        elif record.slug == "estate-resources":
            # ``backed_up`` is an attribute rather than a column: the core
            # resource kinds declare no such field, and the integration that
            # knows what a backup covers is the one that declares a kind with
            # it. A node is never "uncovered" — nothing backs up a node.
            uncovered = uncovered or any(
                _attributes(entry).get("backed_up") is False and entry.get("kind") != "node"
                for entry in _rows(record.body, "resources")
            )

    return Awkwardness(
        volume_above_ceiling=volume,
        disabled_backup_job=disabled,
        failed_units=units,
        unknown_datastore=unknown,
        uncovered_guest=uncovered,
    )


def _ordered(record: CapturedRecord) -> Iterator[Implausibility]:
    for key in ("turns", "events"):
        rows = list(_rows(record.body, key))
        if not rows:
            continue
        sequences = [_number(row.get("sequence") or row.get("ordinal")) for row in rows]
        if sequences != sorted(sequences):
            yield Implausibility(record.slug, f"/{key}", "they are not in order")
        moments = [
            instant
            for instant in (
                _instant(row.get("occurred_at") or row.get("started_at")) for row in rows
            )
            if instant is not None
        ]
        if moments != sorted(moments):
            yield Implausibility(record.slug, f"/{key}", "their timestamps go backwards")


def _rows(body: Any, key: str) -> Iterator[Mapping[str, Any]]:
    if not isinstance(body, Mapping):
        return
    rows = body.get(key)
    if isinstance(rows, Sequence) and not isinstance(rows, str | bytes):
        for item in rows:
            if isinstance(item, Mapping):
                yield item


def _percentages(value: Any) -> Iterator[float]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if "percent" in str(key).lower() and isinstance(item, int | float):
                yield float(item)
            else:
                yield from _percentages(item)
    elif isinstance(value, Sequence) and not isinstance(value, str | bytes):
        for item in value:
            yield from _percentages(item)


def _leaves(value: Any) -> int:
    if isinstance(value, Mapping):
        return sum(_leaves(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return sum(_leaves(item) for item in value)
    return 1


def _arguments_key(record: CapturedRecord) -> str:
    return ",".join(f"{key}={value}" for key, value in sorted(record.arguments.items()))


def _instant(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _number(value: Any) -> float:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0.0


__all__ = [
    "Awkwardness",
    "Distribution",
    "Implausibility",
    "awkwardness_of",
    "distribution_of",
    "implausibilities",
]
