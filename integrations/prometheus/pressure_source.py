"""Reading resource pressure for a whole estate, from the host's own series.

``pressure.py`` decides *what* to ask — which series answers pressure for a
guest, and why it must be the host's rather than the guest's. This asks it, for
a set of resources at once, and hands back readings the poller can store.

**One call per series, not per guest.** A cluster of seventy-two guests asked
one at a time is two hundred and sixteen provider calls a tick, and a source
whose cost grows with the estate is one an operator has to think about before
watching anything. The exporter labels every series with the guest it is about,
so a single query with a matcher over the set returns all of them — which is the
property ``MetricsQuerySource`` already documents about itself and the reason
this shape was chosen over the obvious loop.

**The matcher is anchored to the guests this deployment holds.** ``id=~"lxc/.+"``
would answer for every container on the cluster, including ones the estate does
not watch, and the readings would be attributed to nobody.

**A guest with no answer is absent, never zero.** A nought meaning "no data"
fires every below-threshold detector in the deployment at once.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from integrations.prometheus.pressure import (
    GUEST_CPU_USED,
    GUEST_DISK_TOTAL,
    GUEST_DISK_USED,
    GUEST_ID_LABEL,
    GUEST_MEMORY_TOTAL,
    GUEST_MEMORY_USED,
)
from integrations.prometheus.schema import INTEGRATION
from platform.estate.kinds import KIND_CONTAINER, KIND_VIRTUAL_MACHINE
from platform.observation.sources.port import (
    PollBudget,
    SignalDeclaration,
    SignalPage,
    SignalReading,
)
from platform.persistence.ports.signal_store import SignalKind

#: How each guest kind spells itself in the exporter's identifier.
_PREFIXES: Mapping[str, str] = {KIND_CONTAINER: "lxc", KIND_VIRTUAL_MACHINE: "qemu"}

#: The three readings pressure is, and the expression each is answered by. A
#: ratio rather than a raw number for two of them, because "94% full" is what a
#: detector threshold is written against and a byte count needs the capacity
#: beside it to mean anything.
_SERIES: Mapping[str, tuple[str, str]] = {
    "cpu": (GUEST_CPU_USED, ""),
    "memory": (GUEST_MEMORY_USED, GUEST_MEMORY_TOTAL),
    "disk": (GUEST_DISK_USED, GUEST_DISK_TOTAL),
}

#: How often this is worth asking. Matches the exporter's own scrape interval:
#: asking faster returns the same sample twice and spends a provider call to do
#: it.
DEFAULT_INTERVAL_SECONDS = 60


@runtime_checkable
class PrometheusQuery(Protocol):
    """Whatever can answer one PromQL expression."""

    async def evaluate(self, expression: str) -> Sequence[Mapping[str, Any]]:
        """Return Prometheus' own ``result`` list for ``expression``."""


def guest_id_for(kind: str, *, vmid: int) -> str:
    """Return the exporter's identifier for one guest, or empty for a kind with none.

    Empty rather than a guess: a node is the host and publishes its own series
    under a different shape, and a matcher built from an empty identity would
    match everything.
    """
    prefix = _PREFIXES.get(kind, "")
    return f"{prefix}/{vmid}" if prefix and vmid else ""


def guests_by_prefix(guests: Sequence[str]) -> dict[str, tuple[str, ...]]:
    """Group guest identifiers by their kind prefix, in the order given.

    One query per prefix rather than one over both: a container and a virtual
    machine spell themselves differently, and a single alternation over the two
    is a regular expression nobody reviewing this can read.
    """
    grouped: dict[str, list[str]] = {}
    for guest in guests:
        prefix, _, _ = guest.partition("/")
        if prefix:
            grouped.setdefault(prefix, []).append(guest)
    return {prefix: tuple(found) for prefix, found in grouped.items()}


def guest_matcher(guests: Sequence[str]) -> str:
    """Return the ``id`` matcher covering exactly ``guests``.

    Anchored to the identifiers given rather than to a wildcard, so a reading
    can never arrive for a guest this deployment does not watch.
    """
    if not guests:
        return ""
    prefix, _, _ = guests[0].partition("/")
    numbers = "|".join(guest.partition("/")[2] for guest in guests)
    return f"{prefix}/({numbers})"


def _expression(metric: str, matcher: str) -> str:
    return (
        f'{metric}{{{GUEST_ID_LABEL}="{matcher}"}}'
        if "|" not in matcher
        else (f'{metric}{{{GUEST_ID_LABEL}=~"{matcher}"}}')
    )


def _ratio(used: str, total: str, matcher: str) -> str:
    """Return the used-over-capacity expression, as a fraction of one."""
    return f"{_expression(used, matcher)} / {_expression(total, matcher)}"


@dataclass(frozen=True, slots=True)
class PressureSignalSource:
    """Pressure for a set of estate resources, read from the host's exporter."""

    client: PrometheusQuery
    #: Estate resource identifier to the exporter's identifier for the same
    #: guest. Handed in rather than derived, because the mapping needs the
    #: estate and this package may not read one.
    guests: Mapping[str, str] = field(default_factory=dict)
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS

    @property
    def declaration(self) -> SignalDeclaration:
        """Return what this source says about itself before it is polled."""
        return SignalDeclaration(
            source=INTEGRATION,
            signals=tuple(_SERIES),
            interval_seconds=self.interval_seconds,
            # Three series, and one call each per guest prefix. A mixed estate
            # costs six; a homogeneous one costs three.
            max_provider_calls=len(_SERIES) * len(_PREFIXES),
        )

    async def read(
        self,
        *,
        resource_ids: tuple[str, ...],
        at: datetime,
        budget: PollBudget,
    ) -> SignalPage:
        """Return one reading per resource per series the exporter answered for."""
        del at, budget  # the cost is bounded by the series count, not the estate
        wanted = {
            self.guests[resource_id]: resource_id
            for resource_id in resource_ids
            if self.guests.get(resource_id)
        }
        if not wanted:
            return SignalPage(readings=(), provider_calls=0)

        readings: list[SignalReading] = []
        calls = 0
        for guests in guests_by_prefix(tuple(wanted)).values():
            matcher = guest_matcher(guests)
            for name, (used, total) in _SERIES.items():
                expression = _ratio(used, total, matcher) if total else _expression(used, matcher)
                calls += 1
                for series in await self.client.evaluate(expression):
                    reading = _reading(series, name=name, wanted=wanted)
                    if reading is not None:
                        readings.append(reading)

        return SignalPage(readings=tuple(readings), provider_calls=calls)


def _reading(
    series: Mapping[str, Any], *, name: str, wanted: Mapping[str, str]
) -> SignalReading | None:
    """Return the reading one returned series is, or ``None`` if it is not ours.

    A series whose identifier nobody asked about is dropped rather than
    attributed: the matcher should have prevented it, and inventing an owner
    for it would put somebody else's number on a resource.
    """
    labels = series.get("metric") or {}
    guest = str(labels.get(GUEST_ID_LABEL, ""))
    resource_id = wanted.get(guest)
    if resource_id is None:
        return None
    value = series.get("value") or ()
    if len(value) < 2:
        return None
    try:
        number = float(value[1])
    except (TypeError, ValueError):
        return None
    return SignalReading(
        name=name,
        resource_id=resource_id,
        kind=SignalKind.NUMBER,
        value=number,
        labels={GUEST_ID_LABEL: guest},
    )


__all__ = [
    "DEFAULT_INTERVAL_SECONDS",
    "PressureSignalSource",
    "PrometheusQuery",
    "guest_id_for",
    "guest_matcher",
    "guests_by_prefix",
]
