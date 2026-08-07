"""What a cloud run is allowed to cost, and what it actually did.

Both halves, because either one alone is useless. A bound with no actual is a
comment; an actual with no bound is a number nobody knows how to react to.

The estimate is deliberately simple: each resource declares an hourly rate, the
run declares how long it lasted, and the product is what is reported. It will
not agree with the invoice to the cent — data transfer, request counts, and
per-second billing minima all move it — and it is not trying to. What it has to
be is *monotonic in the thing that goes wrong*: a run that leaked a cluster for
six hours reports six times a run that tore it down, which is the signal
somebody needs before the invoice arrives a month later.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from config.constants.chaos import (
    CLOUD_SCENARIO_COST_BOUNDS_USD,
    CLOUD_SUITE_COST_BOUND_USD,
)

#: The smallest run this suite bills for. Cloud providers charge a minimum for
#: anything they start, and reporting a two-second run as costing nothing would
#: make a leak look like a rounding error.
MINIMUM_BILLED_SECONDS = 60.0


@dataclass(frozen=True, slots=True)
class RatedResource:
    """One provisioned resource and what an hour of it costs."""

    kind: str
    hourly_usd: float
    count: int = 1

    @property
    def hourly_total_usd(self) -> float:
        """Return what an hour of every copy of this resource costs."""
        return self.hourly_usd * self.count


@dataclass(frozen=True, slots=True)
class CostReport:
    """What one cloud scenario cost, against what it was allowed to."""

    scenario_id: str
    bound_usd: float
    actual_usd: float
    duration_seconds: float
    resources: tuple[RatedResource, ...] = field(default_factory=tuple)

    @property
    def within(self) -> bool:
        """Return whether the run stayed inside its declared bound."""
        return self.actual_usd <= self.bound_usd

    @property
    def overrun_usd(self) -> float:
        """Return how far over the bound the run went, or zero."""
        return max(0.0, self.actual_usd - self.bound_usd)

    @property
    def headroom(self) -> float:
        """Return the share of the bound the run did not use."""
        if self.bound_usd <= 0:
            return 0.0
        return max(0.0, 1.0 - self.actual_usd / self.bound_usd)

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this cost."""
        return {
            "scenario": self.scenario_id,
            "bound_usd": round(self.bound_usd, 4),
            "actual_usd": round(self.actual_usd, 4),
            "within": self.within,
            "overrun_usd": round(self.overrun_usd, 4),
            "duration_seconds": round(self.duration_seconds, 1),
            "resources": [
                {"kind": found.kind, "count": found.count, "hourly_usd": found.hourly_usd}
                for found in self.resources
            ],
        }

    def render(self) -> str:
        """Return the one line a run prints about what it spent."""
        verdict = "within" if self.within else f"OVER by ${self.overrun_usd:.2f}"
        return (
            f"{self.scenario_id}: ${self.actual_usd:.2f} of ${self.bound_usd:.2f} "
            f"over {self.duration_seconds / 60:.0f}m — {verdict}"
        )


def bound_for(scenario_id: str) -> float:
    """Return what one run of ``scenario_id`` is allowed to cost.

    Raises:
        KeyError: a scenario with no declared bound. Deliberately fatal — an
            unbounded cloud scenario is the thing this module exists to prevent,
            and defaulting it to something would hide the omission.
    """
    return CLOUD_SCENARIO_COST_BOUNDS_USD[scenario_id]


def estimate_usd(resources: Sequence[RatedResource], *, duration_seconds: float) -> float:
    """Return what ``resources`` cost for ``duration_seconds``."""
    billed = max(duration_seconds, MINIMUM_BILLED_SECONDS)
    hourly = sum(found.hourly_total_usd for found in resources)
    return hourly * billed / 3600.0


def report_cost(
    scenario_id: str,
    resources: Sequence[RatedResource],
    *,
    duration_seconds: float,
    bound_usd: float | None = None,
) -> CostReport:
    """Return what one scenario cost, against the bound it declared."""
    return CostReport(
        scenario_id=scenario_id,
        bound_usd=bound_usd if bound_usd is not None else bound_for(scenario_id),
        actual_usd=estimate_usd(resources, duration_seconds=duration_seconds),
        duration_seconds=duration_seconds,
        resources=tuple(resources),
    )


@dataclass(frozen=True, slots=True)
class SuiteCostReport:
    """What a whole cloud run cost, against the suite's own ceiling."""

    reports: tuple[CostReport, ...] = field(default_factory=tuple)
    bound_usd: float = CLOUD_SUITE_COST_BOUND_USD

    @property
    def actual_usd(self) -> float:
        """Return what every scenario cost together."""
        return sum(report.actual_usd for report in self.reports)

    @property
    def within(self) -> bool:
        """Return whether the whole run stayed inside the suite ceiling."""
        return self.actual_usd <= self.bound_usd and all(report.within for report in self.reports)

    @property
    def over_bound(self) -> tuple[str, ...]:
        """Return the scenarios that went over their own bound."""
        return tuple(report.scenario_id for report in self.reports if not report.within)

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this suite's cost."""
        return {
            "bound_usd": round(self.bound_usd, 4),
            "actual_usd": round(self.actual_usd, 4),
            "within": self.within,
            "over_bound": list(self.over_bound),
            "scenarios": [report.to_record() for report in self.reports],
        }

    def render(self) -> str:
        """Return the cost section of a suite report."""
        lines = [report.render() for report in self.reports]
        verdict = "within" if self.within else "OVER"
        lines.append(f"suite total: ${self.actual_usd:.2f} of ${self.bound_usd:.2f} — {verdict}")
        return "\n".join(lines)


__all__ = [
    "MINIMUM_BILLED_SECONDS",
    "CostReport",
    "RatedResource",
    "SuiteCostReport",
    "bound_for",
    "estimate_usd",
    "report_cost",
]
