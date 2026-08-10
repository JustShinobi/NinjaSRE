"""Building a guest's resource-usage query from the host's series, not the guest's.

Every other module in this package is about Prometheus. This one is about a
correctness rule the estate holds and Prometheus cannot know: for a container,
the counters visible *inside* the guest are the host's cgroup accounting seen
through a namespace that was never built to publish it. A query aimed there
answers, and answers wrongly.

The rule is not restated here. It is read from
``platform.estate.signal_map``, which is the single place it lives — so a query
built by this module and a resource page rendered from the same map cannot
disagree, and switching the map off is a thing that can be measured rather than
argued about.

``IN_GUEST_SERIES`` exists to be asserted against. The failure it names has no
observable signature in a result: a query on ``node_memory_MemAvailable_bytes``
inside an LXC guest returns a well-formed series with a plausible number in it,
and nothing downstream can tell it apart from the right one. So the names are
declared, and a test holds that none of them appears in a query this module
builds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from config.constants.signals import (
    SIGNAL_KEY_INSTANCE,
    SIGNAL_KEY_VMID,
    SIGNAL_QUESTION_PRESSURE,
)
from integrations.prometheus.schema import INTEGRATION
from platform.estate.kinds import KIND_CONTAINER, KIND_VIRTUAL_MACHINE
from platform.estate.signal_map import SignalSource, signal_map_for
from platform.persistence.ports.estate_repository import Resource

#: The exporter's own label for one guest, which is how the host publishes it.
#: ``lxc/100`` and ``qemu/201`` — the kind and the identifier together, because
#: a container and a virtual machine may share a number.
GUEST_ID_LABEL: Final = "id"

#: How each guest kind spells itself in that label.
_GUEST_PREFIXES: Final[dict[str, str]] = {
    KIND_CONTAINER: "lxc",
    KIND_VIRTUAL_MACHINE: "qemu",
}

#: The series the *host* publishes about a guest. Named as constants so a
#: rename in the exporter is one edit here rather than four string literals in
#: three modules.
GUEST_MEMORY_USED: Final = "pve_memory_usage_bytes"
GUEST_MEMORY_TOTAL: Final = "pve_memory_size_bytes"
GUEST_CPU_USED: Final = "pve_cpu_usage_ratio"
GUEST_DISK_USED: Final = "pve_disk_usage_bytes"
GUEST_DISK_TOTAL: Final = "pve_disk_size_bytes"
GUEST_UP: Final = "pve_up"

#: The series a node publishes about itself. A node *is* the host, so its own
#: exporter is the right source and there is no misattribution to avoid.
NODE_MEMORY_AVAILABLE: Final = "node_memory_MemAvailable_bytes"
NODE_MEMORY_TOTAL: Final = "node_memory_MemTotal_bytes"
NODE_CPU_SECONDS: Final = "node_cpu_seconds_total"
NODE_FILESYSTEM_AVAILABLE: Final = "node_filesystem_avail_bytes"
NODE_FILESYSTEM_SIZE: Final = "node_filesystem_size_bytes"

#: Every host-side series a guest query may be built from.
HOST_SIDE_SERIES: Final[tuple[str, ...]] = (
    GUEST_MEMORY_USED,
    GUEST_MEMORY_TOTAL,
    GUEST_CPU_USED,
    GUEST_DISK_USED,
    GUEST_DISK_TOTAL,
    GUEST_UP,
)

#: What a guest query must never read, and why the list is here rather than in a
#: comment: each of these is published by a collector *inside* a machine, and
#: inside an LXC container each of them reports the host's figures under the
#: guest's name. The number that comes back is well-formed, plausible, and
#: about something else.
IN_GUEST_SERIES: Final[tuple[str, ...]] = (
    NODE_MEMORY_AVAILABLE,
    NODE_MEMORY_TOTAL,
    NODE_CPU_SECONDS,
    NODE_FILESYSTEM_AVAILABLE,
    NODE_FILESYSTEM_SIZE,
    "container_memory_usage_bytes",
    "container_memory_working_set_bytes",
    "container_cpu_usage_seconds_total",
)


@dataclass(frozen=True, slots=True)
class PressureQuery:
    """One PromQL expression, and what it is being asked to establish."""

    name: str
    promql: str
    question: str

    def to_record(self) -> dict[str, str]:
        """Return the JSON-serialisable form a result carries."""
        return {"name": self.name, "promql": self.promql, "question": self.question}


def pressure_source(kind: str, *, vmid: int = 0, address: str = "") -> SignalSource | None:
    """Return what the signal map says answers *pressure* for this resource shape.

    Built from a resource rather than from a rule spelled here, so the answer is
    the same one the resource page shows. ``None`` means the map declined —
    either this kind has no resource-usage series, or the estate holds no key to
    filter one by — and declining is the point: a selector with an empty key
    matches every guest on the cluster, and the answer that comes back is a
    number.
    """
    attributes: dict[str, object] = {}
    if vmid:
        attributes["vmid"] = vmid
    if address:
        attributes["address"] = address
    resource = Resource(
        resource_id=f"{kind}:{vmid or address or 'unkeyed'}",
        kind=kind,
        source="proxmox",
        native_id=f"{kind}/{vmid or address}",
        attributes=attributes,
    )
    return signal_map_for(resource, configured=(INTEGRATION, "proxmox")).source_for(
        SIGNAL_QUESTION_PRESSURE
    )


def pressure_queries(source: SignalSource, *, kind: str) -> tuple[PressureQuery, ...]:
    """Return the expressions that answer *pressure* for what ``source`` names.

    ``kind`` is the resource's kind, which decides how the host's exporter spells
    this guest in its own label. Passed rather than carried on the map entry
    because the entry is about the *answer* — which source, which key — and the
    subject is what the caller already had when it asked.

    Raises:
        ValueError: ``source`` does not name Prometheus, or names a key this
            module has no series for. Refused rather than defaulted, because a
            default here is how a guest query quietly becomes a node query.
    """
    if source.integration != INTEGRATION:
        raise ValueError(
            f"this builds Prometheus queries and the map named {source.integration!r}. "
            f"Building one anyway would put a PromQL expression in front of a vendor that "
            f"does not speak it."
        )
    if source.keyed_by == SIGNAL_KEY_VMID:
        return _guest_queries(source, kind)
    if source.keyed_by == SIGNAL_KEY_INSTANCE:
        return _node_queries(source)
    raise ValueError(
        f"no pressure series is keyed by {source.keyed_by!r}. A query built on the wrong "
        f"label matches nothing, which reads as a resource under no pressure."
    )


def _guest_queries(source: SignalSource, kind: str) -> tuple[PressureQuery, ...]:
    """Return the host-side expressions for one guest, filtered by its own identifier."""
    prefix = _prefix_for(kind)
    selector = f'{{{GUEST_ID_LABEL}="{prefix}/{source.key}"}}'
    return (
        PressureQuery(
            name="memory",
            promql=f"{GUEST_MEMORY_USED}{selector} / {GUEST_MEMORY_TOTAL}{selector}",
            question=(
                "how much of its own memory ceiling this guest is using, as the host "
                "accounts for it — which is the accounting the host enforces the limit by"
            ),
        ),
        PressureQuery(
            name="cpu",
            promql=f"{GUEST_CPU_USED}{selector}",
            question="how much CPU the host is giving this guest",
        ),
        PressureQuery(
            name="disk",
            promql=f"{GUEST_DISK_USED}{selector} / {GUEST_DISK_TOTAL}{selector}",
            question="how full the volume the host gave this guest is",
        ),
    )


def _node_queries(source: SignalSource) -> tuple[PressureQuery, ...]:
    """Return the expressions for a node, which publishes about itself."""
    selector = f'{{instance=~"{source.key}.*"}}'
    return (
        PressureQuery(
            name="memory",
            promql=(f"1 - ({NODE_MEMORY_AVAILABLE}{selector} / {NODE_MEMORY_TOTAL}{selector})"),
            question="how much of this node's memory is committed",
        ),
        PressureQuery(
            name="cpu",
            promql=f'1 - rate({NODE_CPU_SECONDS}{{instance=~"{source.key}.*",mode="idle"}}[5m])',
            question="how much of this node's CPU is in use",
        ),
        PressureQuery(
            name="disk",
            promql=(
                f"1 - ({NODE_FILESYSTEM_AVAILABLE}{selector} / {NODE_FILESYSTEM_SIZE}{selector})"
            ),
            question="how full this node's filesystems are",
        ),
    )


def _prefix_for(kind: str) -> str:
    """Return how the host's exporter spells this guest's kind in its label."""
    prefix = _GUEST_PREFIXES.get(kind)
    if prefix is None:
        raise ValueError(
            f"{kind!r} is keyed by vmid and is not a guest kind this exporter publishes. "
            f"A guessed prefix produces a selector that matches nothing, which reads as a "
            f"guest under no pressure."
        )
    return prefix


__all__ = [
    "GUEST_CPU_USED",
    "GUEST_DISK_TOTAL",
    "GUEST_DISK_USED",
    "GUEST_ID_LABEL",
    "GUEST_MEMORY_TOTAL",
    "GUEST_MEMORY_USED",
    "GUEST_UP",
    "HOST_SIDE_SERIES",
    "IN_GUEST_SERIES",
    "PressureQuery",
    "pressure_queries",
    "pressure_source",
]
