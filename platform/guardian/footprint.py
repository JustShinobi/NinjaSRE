"""What the homelab profile promises about its own size, and how that is judged.

A declared footprint is only worth declaring if something can fail against it.
Two things can, and they answer different questions.

**The container runtime enforces the ceiling.** Each service in the homelab
compose file carries a memory and CPU limit, the four sum to the declared total,
and a contract test holds the file and the constant to each other. That is the
half nobody has to remember.

**A soak judges the idle claim.** The ceiling says what the deployment may not
exceed; the idle figure says what it actually uses when nothing is happening,
and that number is the one an operator cares about because their machine is
already doing something else. It is judged over hours rather than at a point,
because the thing worth catching is growth — a deployment that is fine at minute
one and half a gibibyte heavier at hour twelve has a leak, and a point
measurement cannot see it.

**A soak that did not run long enough says so.** Reporting "within footprint"
after four minutes is a claim about four minutes, and the honest verdict for it
is that there is no verdict yet.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from config.constants.deployment import (
    HOMELAB_CPU_LIMITS,
    HOMELAB_IDLE_MEMORY_MIB,
    HOMELAB_MEMORY_LIMITS_MIB,
    HOMELAB_SOAK_HOURS,
    HOMELAB_TOTAL_CPUS,
    HOMELAB_TOTAL_MEMORY_MIB,
)


@dataclass(frozen=True, slots=True)
class Footprint:
    """What the profile claims about itself, in the units an operator sizes in."""

    total_memory_mib: int = HOMELAB_TOTAL_MEMORY_MIB
    total_cpus: float = HOMELAB_TOTAL_CPUS
    idle_memory_mib: int = HOMELAB_IDLE_MEMORY_MIB

    def describe(self) -> str:
        """Return the sentence the profile states about its size."""
        return (
            f"The whole stack runs inside {self.total_memory_mib / 1024:.0f} GiB and "
            f"{self.total_cpus:g} CPUs, enforced as per-container limits rather than "
            f"promised. Idle, it is expected to sit near {self.idle_memory_mib} MiB — well "
            f"under the ceiling, because a deployment at its limit while nothing is "
            f"happening has nothing left for the hour something is."
        )

    def to_record(self) -> dict[str, Any]:
        """Return what a health endpoint reports about the declared footprint."""
        return {
            "total_memory_mib": self.total_memory_mib,
            "total_cpus": self.total_cpus,
            "idle_memory_mib": self.idle_memory_mib,
            "per_service_memory_mib": dict(HOMELAB_MEMORY_LIMITS_MIB),
            "per_service_cpus": dict(HOMELAB_CPU_LIMITS),
            "description": self.describe(),
        }


@dataclass(frozen=True, slots=True)
class UsageSample:
    """One reading of what the whole deployment is using."""

    at: datetime
    memory_mib: float
    cpus: float = 0.0


@dataclass(frozen=True, slots=True)
class SoakVerdict:
    """What a long-running measurement concluded, including that it cannot yet.

    ``long_enough`` is separate from ``within`` on purpose. A soak that ran for
    four minutes and stayed inside the footprint has established a fact about
    four minutes, and reporting that as "within footprint" is how an optimistic
    declaration survives review.
    """

    within: bool
    long_enough: bool
    hours: float
    peak_memory_mib: float
    #: How much the *floor* moved between the first and last quarter of the run.
    #: The reading that finds a leak: a peak can be one request, and a rising
    #: floor cannot.
    memory_growth_mib: float
    samples: int
    breached_at: datetime | None = None

    @property
    def conclusive(self) -> bool:
        """Return whether this verdict is worth reporting as one."""
        return self.long_enough and self.samples > 0

    def describe(self, footprint: Footprint) -> str:
        """Return what the soak is reported as."""
        if not self.samples:
            return "Nothing was measured, so there is nothing to conclude."
        if not self.long_enough:
            return (
                f"Measured for {self.hours:.1f} hours, which is short of the "
                f"{HOMELAB_SOAK_HOURS:g} a footprint claim is judged over. Memory growth "
                f"is what this is looking for and it does not show up this early, so "
                f"there is no verdict yet."
            )
        if not self.within:
            when = f" at {self.breached_at.isoformat()}" if self.breached_at else ""
            return (
                f"Exceeded the declared idle footprint{when}: peaked at "
                f"{self.peak_memory_mib:.0f} MiB against {footprint.idle_memory_mib} MiB "
                f"over {self.hours:.1f} hours."
            )
        return (
            f"Stayed inside the declared idle footprint over {self.hours:.1f} hours: "
            f"peaked at {self.peak_memory_mib:.0f} MiB against "
            f"{footprint.idle_memory_mib} MiB, with the floor moving "
            f"{self.memory_growth_mib:+.0f} MiB between the first and last quarter."
        )


def assess(
    samples: Sequence[UsageSample],
    *,
    footprint: Footprint | None = None,
    required_hours: float = HOMELAB_SOAK_HOURS,
) -> SoakVerdict:
    """Return what ``samples`` say about the deployment staying inside its footprint.

    The floor of each quarter rather than its mean, because a mean over an
    interval that contained one investigation is a mean about that
    investigation. What a leak moves is the number the deployment never goes
    below.
    """
    declared = footprint or Footprint()
    if not samples:
        return SoakVerdict(
            within=True,
            long_enough=False,
            hours=0.0,
            peak_memory_mib=0.0,
            memory_growth_mib=0.0,
            samples=0,
        )

    ordered = sorted(samples, key=lambda sample: sample.at)
    span: timedelta = ordered[-1].at - ordered[0].at
    hours = span.total_seconds() / 3_600

    peak = max(sample.memory_mib for sample in ordered)
    breach = next(
        (sample.at for sample in ordered if sample.memory_mib > declared.idle_memory_mib),
        None,
    )

    quarter = max(1, len(ordered) // 4)
    first_floor = min(sample.memory_mib for sample in ordered[:quarter])
    last_floor = min(sample.memory_mib for sample in ordered[-quarter:])

    return SoakVerdict(
        within=breach is None,
        long_enough=hours >= required_hours,
        hours=hours,
        peak_memory_mib=peak,
        memory_growth_mib=last_floor - first_floor,
        samples=len(ordered),
        breached_at=breach,
    )


__all__ = ["Footprint", "SoakVerdict", "UsageSample", "assess"]
