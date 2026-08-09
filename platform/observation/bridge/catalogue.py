"""What a resource exposes once the join has been made: its series and its logs.

FR-004 and FR-013 are one idea from two directions. An investigation into a
guest should be able to ask for that guest's metrics and that guest's logs
without composing a Prometheus selector or a Loki stream selector, because
making it compose one means the agent has to learn two query languages before it
can look at anything — and a wrong query in either of them comes back empty,
which reads exactly like a healthy guest.

**The metric side is a lookup, not a query.** The mapping pass already decided
which series describe which resource, so asking for a resource's metrics is
reading that answer. Each entry carries the selector that would read it again,
so a history read has something to ask with and the caller still never writes
one.

**The log side is a declared selector per resource kind.** Log labels are a
deployment's own convention — one estate labels a container stream by VMID and
another by hostname — so the rules are configuration with shipped defaults for
the shapes a Proxmox homelab gets from the journal. A kind with no declared
selector returns nothing rather than a guess, because a guessed selector queries
a stream that may not exist and comes back empty, which reads as a quiet guest.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from config.constants.observability_bridge import MAX_SERIES_PER_RESOURCE
from platform.estate.kinds import KIND_CONTAINER, KIND_NODE, KIND_VIRTUAL_MACHINE
from platform.observation.bridge.mapping import SeriesMapping, SeriesView
from platform.persistence.ports.estate_repository import Resource

#: ``{name}`` is the resource's display name; ``{native:<index>}`` is one
#: ``/``-separated segment of its native identity, negative counting from the
#: end. The same two-form grammar the label rules use, for the same reason: a
#: template that could compute would be a query language.
_PLACEHOLDER: Final = re.compile(r"\{(name|native)(?::(-?\d+))?\}")


@dataclass(frozen=True, slots=True)
class LogSelectorRule:
    """The stream selector that applies to one kind of resource.

    ``template`` is written in the log system's own selector syntax with the
    resource's identity substituted in. This package does not parse it: an
    operator whose promtail labels streams some third way writes their own rule
    and it works, which is the property a normalised form would lose.
    """

    rule_id: str
    resource_kind: str
    template: str
    description: str = ""

    def selector_for(self, resource: Resource) -> str:
        """Return the selector for ``resource``, or the empty string if it cannot be built.

        A placeholder that resolved to nothing loses the selector rather than
        narrowing it: ``{{container=""}}`` is a valid query that matches nothing,
        and a query matching nothing reads exactly like a quiet guest.
        """
        empty = False

        def substitute(match: re.Match[str]) -> str:
            nonlocal empty
            if match.group(1) == "name":
                value = resource.display_name
            else:
                segments = resource.native_id.split("/")
                index = int(match.group(2) or "-1")
                value = segments[index] if -len(segments) <= index < len(segments) else ""
            empty = empty or not value
            return value

        resolved = _PLACEHOLDER.sub(substitute, self.template)
        return "" if empty else resolved


#: What a Proxmox homelab gets from the journal with no extra configuration. The
#: node's own hostname for a node, the guest's VMID for a guest — which is what
#: ``pve-container`` and ``qemu-server`` already tag their journal entries with.
SHIPPED_LOG_SELECTORS: Final[tuple[LogSelectorRule, ...]] = (
    LogSelectorRule(
        rule_id="journal-node",
        resource_kind=KIND_NODE,
        template='{job="systemd-journal", host="{native:-1}"}',
        description=(
            "a node's own journal, selected by its hostname — the last segment of its "
            "estate identity, which is the name corosync knows it by"
        ),
    ),
    LogSelectorRule(
        rule_id="journal-container",
        resource_kind=KIND_CONTAINER,
        template='{job="systemd-journal"} |= "pve-container@{native:-1}"',
        description=(
            "a container's lifecycle as the host journal records it, selected by VMID. "
            "The container's own logs are inside it and reach Loki only if something "
            "in the guest ships them"
        ),
    ),
    LogSelectorRule(
        rule_id="journal-virtual-machine",
        resource_kind=KIND_VIRTUAL_MACHINE,
        template='{job="systemd-journal"} |= "qemu-server: VM {native:-1}"',
        description="a virtual machine's lifecycle as the host journal records it, by VMID",
    ),
)


@dataclass(frozen=True, slots=True)
class ResourceSeries:
    """One series a resource exposes, and what it last read."""

    resource_id: str
    metric: str
    labels: Mapping[str, str]
    view: SeriesView
    rule_id: str
    latest_value: float | None = None
    latest_at: datetime | None = None

    @property
    def matcher(self) -> str:
        """Return the selector that would read this series again.

        The one piece of query grammar this package writes, and it is the
        label-matcher form every Prometheus-compatible source accepts. Written
        here rather than by the caller because the alternative is an
        investigation composing selectors, which is what FR-004 exists to avoid.
        """
        if not self.labels:
            return self.metric
        inner = ",".join(f'{name}="{value}"' for name, value in sorted(self.labels.items()))
        return f"{self.metric}{{{inner}}}"


@dataclass(frozen=True, slots=True)
class ResourceLogStream:
    """The log stream that applies to one resource, and the rule that says so."""

    resource_id: str
    selector: str
    rule_id: str


@dataclass(frozen=True, slots=True)
class ResourceObservability:
    """Everything the bridge can say about one resource, indexed by resource.

    Built from a mapping pass rather than holding one, so a stale catalogue is
    visibly a stale object rather than a query that quietly returns last hour's
    join.
    """

    series_by_resource: Mapping[str, tuple[ResourceSeries, ...]] = field(default_factory=dict)
    streams_by_resource: Mapping[str, ResourceLogStream] = field(default_factory=dict)

    @classmethod
    def of(
        cls,
        mapping: SeriesMapping,
        *,
        resources: Iterable[Resource],
        log_selectors: Sequence[LogSelectorRule] = SHIPPED_LOG_SELECTORS,
    ) -> ResourceObservability:
        """Return the catalogue ``mapping`` and ``resources`` describe."""
        by_resource: dict[str, list[ResourceSeries]] = {}
        for entry in mapping.mapped:
            found = by_resource.setdefault(entry.resource_id, [])
            if len(found) >= MAX_SERIES_PER_RESOURCE:
                continue
            newest = entry.series.newest
            found.append(
                ResourceSeries(
                    resource_id=entry.resource_id,
                    metric=entry.metric,
                    labels=entry.labels,
                    view=entry.view,
                    rule_id=entry.rule_id,
                    latest_value=newest.value if newest else None,
                    latest_at=newest.observed_at if newest else None,
                )
            )

        streams: dict[str, ResourceLogStream] = {}
        for resource in resources:
            for rule in log_selectors:
                if rule.resource_kind != resource.kind:
                    continue
                selector = rule.selector_for(resource)
                if selector:
                    streams[resource.resource_id] = ResourceLogStream(
                        resource_id=resource.resource_id,
                        selector=selector,
                        rule_id=rule.rule_id,
                    )
                break

        return cls(
            series_by_resource={key: tuple(value) for key, value in by_resource.items()},
            streams_by_resource=streams,
        )

    def metrics_for(self, resource_id: str) -> tuple[ResourceSeries, ...]:
        """Return the series that describe ``resource_id``, newest value each."""
        return self.series_by_resource.get(resource_id, ())

    def log_selector_for(self, resource_id: str) -> ResourceLogStream | None:
        """Return the stream selector for ``resource_id``, or ``None`` if none applies."""
        return self.streams_by_resource.get(resource_id)


__all__ = [
    "SHIPPED_LOG_SELECTORS",
    "LogSelectorRule",
    "ResourceLogStream",
    "ResourceObservability",
    "ResourceSeries",
]
