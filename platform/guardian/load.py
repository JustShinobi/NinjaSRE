"""What watching costs the cluster, declared as a number and measured against it.

NFR-002 asks that detection add no load the cluster itself notices, and that the
total call rate be *declared and measured*. Both halves matter, and the reason
they do is specific to this deployment shape: a Proxmox cluster's API is a Perl
daemon on somebody's own hardware, running beside everything else they own. A
monitoring system that made it slow would have produced the incident it exists
to prevent.

The declaration is derived rather than configured. Each shipped signal source
says how often it polls and how many provider calls one poll makes; the rate is
the sum, and it moves when a detector is added rather than when somebody
remembers to update a number. A configured figure would be the one thing in this
module guaranteed to be wrong.

**Readings the operator's own monitoring already publishes cost the cluster
nothing.** They are one range query against a metrics system that scraped the
node anyway. That is why the origin is on the shipped detector: it is what makes
"add ten more detectors from the exporter" a decision with no cost attached, and
"poll ten more things from the API" one with a cost.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from config.constants.guardian import (
    MAX_CLUSTER_CALLS_PER_MINUTE,
    SHIPPED_SIGNAL_INTERVAL_SECONDS,
)
from platform.guardian.catalogue import SHIPPED_DETECTORS, ShippedDetector, SignalOrigin


@dataclass(frozen=True, slots=True)
class SignalSource:
    """One reading the shipped set needs, and what fetching it costs.

    One source per signal name rather than per detector, because two detectors
    over the same reading — the datastore at 85% and the same datastore at 95% —
    are two verdicts from one poll. Counting them separately would declare twice
    the load the deployment actually creates.
    """

    signal: str
    origin: SignalOrigin
    interval_seconds: int = SHIPPED_SIGNAL_INTERVAL_SECONDS
    #: Provider calls one poll of this source makes. One, for both origins: a
    #: hypervisor reading is one cluster-wide endpoint and a published reading is
    #: one range query covering every series the matcher selects.
    calls_per_poll: int = 1
    matcher: str = ""

    @property
    def calls_per_minute(self) -> float:
        """Return how often this source calls whatever answers it."""
        return self.calls_per_poll * 60.0 / self.interval_seconds

    @property
    def costs_the_cluster(self) -> bool:
        """Return whether this source's calls land on the hypervisor itself."""
        return self.origin is SignalOrigin.HYPERVISOR


@dataclass(frozen=True, slots=True)
class LoadDeclaration:
    """What the shipped set costs, split by who pays for it."""

    sources: tuple[SignalSource, ...]
    limit_per_minute: float = MAX_CLUSTER_CALLS_PER_MINUTE

    @property
    def cluster_calls_per_minute(self) -> float:
        """Return the calls per minute this deployment makes to the hypervisor."""
        return sum(source.calls_per_minute for source in self.sources if source.costs_the_cluster)

    @property
    def published_calls_per_minute(self) -> float:
        """Return the calls per minute made to the operator's own metrics system."""
        return sum(
            source.calls_per_minute for source in self.sources if not source.costs_the_cluster
        )

    @property
    def within_declared_bound(self) -> bool:
        """Return whether the cluster's share stays inside what was declared."""
        return self.cluster_calls_per_minute <= self.limit_per_minute

    def describe(self) -> str:
        """Return the sentence an operator is shown about what watching costs them."""
        return (
            f"Detection makes {self.cluster_calls_per_minute:.1f} calls a minute to the "
            f"cluster — {len([s for s in self.sources if s.costs_the_cluster])} readings on "
            f"a {SHIPPED_SIGNAL_INTERVAL_SECONDS // 60}-minute interval, against a declared "
            f"ceiling of {self.limit_per_minute:g}. A further "
            f"{self.published_calls_per_minute:.1f} a minute go to your own metrics system, "
            f"which scraped the nodes anyway and costs the cluster nothing."
        )

    def to_record(self) -> dict[str, Any]:
        """Return what a health report says about detection's own cost."""
        return {
            "cluster_calls_per_minute": round(self.cluster_calls_per_minute, 2),
            "published_calls_per_minute": round(self.published_calls_per_minute, 2),
            "limit_per_minute": self.limit_per_minute,
            "within_declared_bound": self.within_declared_bound,
            "sources": len(self.sources),
            "description": self.describe(),
        }


def shipped_sources(
    catalogue: Sequence[ShippedDetector] = SHIPPED_DETECTORS,
    *,
    interval_seconds: int = SHIPPED_SIGNAL_INTERVAL_SECONDS,
) -> tuple[SignalSource, ...]:
    """Return one source per distinct reading ``catalogue`` needs, in a stable order.

    De-duplicated by signal name, which is the whole point: several detectors
    over one reading are one poll. Ordered by name so a declaration rendered
    twice is the same document twice.
    """
    seen: dict[str, SignalSource] = {}
    for detector in catalogue:
        if detector.signal in seen:
            continue
        seen[detector.signal] = SignalSource(
            signal=detector.signal,
            origin=detector.origin,
            interval_seconds=interval_seconds,
            matcher=detector.matcher,
        )
    return tuple(seen[name] for name in sorted(seen))


def declare_load(
    catalogue: Sequence[ShippedDetector] = SHIPPED_DETECTORS,
    *,
    interval_seconds: int = SHIPPED_SIGNAL_INTERVAL_SECONDS,
) -> LoadDeclaration:
    """Return what the shipped set costs at ``interval_seconds``."""
    return LoadDeclaration(sources=shipped_sources(catalogue, interval_seconds=interval_seconds))


__all__ = ["LoadDeclaration", "SignalSource", "declare_load", "shipped_sources"]
