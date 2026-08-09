"""The three readings that decided an outage and that the Proxmox API does not have.

The reference cluster's only total outage was invisible at every level this
integration can reach. The cluster API said the cluster was fine until it was
not; the guest API said the guests were running; and the thing that had actually
happened — a kernel upgrade renamed the network interfaces, ``ifupdown2`` could
not build ``vmbr0``, and every service that depended on it failed one after
another — was plain in three places, none of which is a REST endpoint:

- a node's **failed systemd units**;
- whether a node's configured **bridges** exist and are up;
- an LVM thin pool's **metadata** percentage, which stops writes while the data
  percentage still looks comfortable.

**The obvious way to get them is forbidden.** They are all one SSH command away,
and a hypervisor integration that could run arbitrary commands on both nodes
would be the single largest authority this system ever held — larger than every
remediation capability combined, because it would subsume them. Article IV
forbids the agent holding an SSH identity at all, so this module spawns nothing,
opens no shell, and reaches no execute endpoint — and a structural test asserts
that absence across the whole package rather than trusting it.

**So they arrive as metrics the node publishes about itself.** A node exporter
with a textfile collector already publishes failed units and bridge state, and a
two-line collector script publishes thin-pool metadata. They reach this system
through the observability bridge, as readings, and the deployment reads them here.

**And where nothing publishes them, they are unavailable — never healthy.**
That is the whole point of this module existing rather than the fields simply
being absent. "Nothing is failing" and "nothing is looking" produce the same
silence and require completely different responses, and a system that cannot tell
them apart will eventually report a fire as fine.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final

from integrations.proxmox.models import METADATA_CRITICAL_PERCENT, Reading
from platform.persistence.ports.estate_repository import ResourceHealth

#: What would publish these readings. Named in every unavailable reading, because
#: "unavailable" with no next step is a dead end and this one has a short fix.
SUPPLEMENTARY_PUBLISHER: Final = (
    "a node exporter with a textfile collector on the Proxmox node, read through the "
    "observability bridge"
)

#: Why the Proxmox API cannot answer these, said once so that every reading can
#: say it without three copies of the sentence.
_NOT_IN_THE_API: Final = (
    "the Proxmox REST API does not expose this, and this integration is forbidden a shell "
    "on the node — the authority that would grant is larger than every remediation "
    "capability put together"
)


@dataclass(frozen=True, slots=True)
class SupplementaryReadings:
    """What a node publishes about itself beyond what its API answers."""

    node: str
    failed_units: Reading[tuple[str, ...]]
    bridges: Reading[Mapping[str, bool]]
    thin_pool_metadata: Reading[Mapping[str, float]]

    @property
    def any_available(self) -> bool:
        """Return whether anything at all is being published for this node."""
        return any(
            reading.available
            for reading in (self.failed_units, self.bridges, self.thin_pool_metadata)
        )

    def health_verdict(self) -> ResourceHealth:
        """Return what these readings say about the node, or that they say nothing.

        ``UNKNOWN`` when nothing is published. Never ``HEALTHY`` for an absent
        reading: an estate that reported "no failed units" for a node nobody is
        watching would be reporting the absence of a monitor as the absence of a
        problem.
        """
        if not self.any_available:
            return ResourceHealth.UNKNOWN
        if self.failed_units.or_else(()):
            return ResourceHealth.DEGRADED
        if any(not up for up in self.bridges.or_else({}).values()):
            return ResourceHealth.UNHEALTHY
        if any(
            percent >= METADATA_CRITICAL_PERCENT
            for percent in self.thin_pool_metadata.or_else({}).values()
        ):
            return ResourceHealth.DEGRADED
        return ResourceHealth.HEALTHY

    def summary(self) -> str:
        """Return the one line a report shows about these three readings."""
        if not self.any_available:
            return (
                f"{self.node}: failed units, bridge state and thin-pool metadata are not "
                f"being published, so nothing is looking at the three readings that "
                f"explained this cluster's worst outage. Install {SUPPLEMENTARY_PUBLISHER}."
            )
        units = self.failed_units.or_else(())
        down = [name for name, up in self.bridges.or_else({}).items() if not up]
        parts = [
            f"{len(units)} failed unit(s)" if units else "no failed units",
            f"bridges down: {', '.join(down)}" if down else "bridges up",
        ]
        return f"{self.node}: {'; '.join(parts)}"

    def signals(self) -> dict[str, str]:
        """Return these readings as estate signals, absent ones included.

        An absent reading becomes a signal saying it is absent rather than no
        signal at all, so a console can render "not being watched" instead of
        rendering nothing and letting a reader assume the best.
        """
        return {
            "failed_units": (
                ",".join(self.failed_units.require())
                if self.failed_units.available
                else "unavailable"
            ),
            "bridges_down": (
                ",".join(name for name, up in self.bridges.require().items() if not up)
                if self.bridges.available
                else "unavailable"
            ),
            "thin_pool_metadata_watched": "yes" if self.thin_pool_metadata.available else "no",
        }


def supplementary_readings(
    *,
    node: str,
    published: Mapping[str, Any] | None,
) -> SupplementaryReadings:
    """Return what is published for ``node``, or three absent readings saying why.

    ``published`` is what the observability bridge found. ``None`` — and any key
    it does not carry — produces an unavailable reading naming the publisher,
    which is what makes the absence actionable rather than merely honest.
    """
    supplied = published or {}
    return SupplementaryReadings(
        node=node,
        failed_units=_reading(supplied, "failed_units", tuple),
        bridges=_reading(supplied, "bridges", dict),
        thin_pool_metadata=_reading(supplied, "thin_pool_metadata", dict),
    )


def _reading(
    published: Mapping[str, Any],
    name: str,
    shape: Callable[[Any], Any],
) -> Reading[Any]:
    """Return one supplementary reading, absent when nothing published it."""
    if name not in published:
        return Reading.missing(
            f"{name.replace('_', ' ')} is not being published for this node: {_NOT_IN_THE_API}",
            published_by=SUPPLEMENTARY_PUBLISHER,
        )
    return Reading.of(shape(published[name]))


__all__ = [
    "SUPPLEMENTARY_PUBLISHER",
    "SupplementaryReadings",
    "supplementary_readings",
]
