"""Whether isolation is working, answered in the four numbers that say so.

health reporting asks for pool size, active sandboxes, provisioning latency, and reaper
status. Those four are not an arbitrary list — each one is the leading indicator
of a distinct failure an operator has to act on differently:

- **pool size against idle count** says the warm pool is exhausted, and the next
  investigation will pay on-demand provisioning latency on the critical path.
- **active count** says how much of the deployment's capacity is committed, which
  is what a burst of correlated alerts consumes first.
- **provisioning latency** is the warm pool's whole justification as a live
  number rather than a test assertion, and its p95 rising while the pool is full means the cluster is the
  bottleneck rather than the pool size.
- **reaper status** is the cost signal. A sweep that keeps skipping instances it
  could not lease means two replicas are fighting; a sweep that has not run means
  orphans are accumulating and nobody is collecting them.

The report also carries the resolved profile's *guarantees* — including where
they are weaker on this operating system — because the honest answer to "is the
sandbox healthy" on a Windows workstation is "it is running, and here is what it
does not enforce".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from config.constants.security import SANDBOX_PROVISIONING_LATENCY_BUDGET_SECONDS
from platform.sandbox.reaper import ReapReport
from platform.sandbox.selection import ProfileGuarantees
from platform.sandbox.spec import SandboxProfile
from platform.sandbox.trace import (
    CollectingSandboxEvents,
    SandboxEventKind,
    latency_percentile,
)


@dataclass(frozen=True, slots=True)
class SandboxHealthReport:
    """The state of the isolation layer, for a health endpoint or the console."""

    profile: SandboxProfile
    guarantees: ProfileGuarantees
    active: int = 0
    pool_size: int = 0
    pool_idle: int = 0
    provisioning_p50_seconds: float | None = None
    provisioning_p95_seconds: float | None = None
    last_sweep: ReapReport | None = None
    observed_at: datetime | None = None

    @property
    def pool_exhausted(self) -> bool:
        """Return whether the next claim would have to provision on demand."""
        return self.pool_size > 0 and self.pool_idle == 0

    @property
    def within_latency_budget(self) -> bool:
        """Return whether provisioning is meeting the deployment's latency target.

        ``True`` when nothing has been provisioned yet. An unmeasured budget is
        not a breached one, and reporting it as breached would make a freshly
        started deployment look broken.
        """
        if self.provisioning_p50_seconds is None:
            return True
        return self.provisioning_p50_seconds <= SANDBOX_PROVISIONING_LATENCY_BUDGET_SECONDS

    @property
    def healthy(self) -> bool:
        """Return whether an operator needs to do anything about the sandbox layer."""
        sweep_clean = self.last_sweep is None or self.last_sweep.clean
        return self.within_latency_budget and sweep_clean and not self.pool_exhausted

    def to_record(self) -> dict[str, object]:
        """Return the JSON-serialisable form a health endpoint serves."""
        return {
            "healthy": self.healthy,
            "profile": str(self.profile),
            "guarantees": self.guarantees.to_record(),
            "active": self.active,
            "pool_size": self.pool_size,
            "pool_idle": self.pool_idle,
            "pool_exhausted": self.pool_exhausted,
            "provisioning_p50_seconds": self.provisioning_p50_seconds,
            "provisioning_p95_seconds": self.provisioning_p95_seconds,
            "within_latency_budget": self.within_latency_budget,
            "last_sweep": None if self.last_sweep is None else self.last_sweep.to_record(),
            "observed_at": None if self.observed_at is None else self.observed_at.isoformat(),
        }


class SandboxHealth:
    """Assembles the report from what the runner and the reaper already recorded.

    It reads rather than measures. A health check that provisioned a sandbox to
    time it would be spending cluster capacity to answer a question the last
    hundred real provisions already answered — and would report a latency nobody
    experienced.
    """

    __slots__ = ("_events", "_guarantees", "_profile")

    def __init__(
        self,
        *,
        profile: SandboxProfile,
        guarantees: ProfileGuarantees,
        events: CollectingSandboxEvents,
    ) -> None:
        self._profile = profile
        self._guarantees = guarantees
        self._events = events

    def report(
        self,
        *,
        active: int = 0,
        pool_size: int = 0,
        pool_idle: int = 0,
        last_sweep: ReapReport | None = None,
        now: datetime | None = None,
    ) -> SandboxHealthReport:
        """Return the current state of the isolation layer."""
        recorded = self._events.events
        return SandboxHealthReport(
            profile=self._profile,
            guarantees=self._guarantees,
            active=active,
            pool_size=pool_size,
            pool_idle=pool_idle,
            provisioning_p50_seconds=latency_percentile(
                recorded, percentile=0.50, kind=SandboxEventKind.PROVISIONED
            ),
            provisioning_p95_seconds=latency_percentile(
                recorded, percentile=0.95, kind=SandboxEventKind.PROVISIONED
            ),
            last_sweep=last_sweep,
            observed_at=now if now is not None else datetime.now(UTC),
        )


__all__ = [
    "SandboxHealth",
    "SandboxHealthReport",
]
