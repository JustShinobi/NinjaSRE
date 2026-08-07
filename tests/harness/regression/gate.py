"""The tolerance policy CI enforces, and the reason it is three policies rather than one.

A gate that fires is only useful if the thing it fired on is real. On a stochastic
system that means a drop has to clear two hurdles, not one:

**The tolerance.** A fixed share, because some movement is expected and gating on
any of it produces a red build every week.

**The uncertainty in both rates.** N attempts give each rate a standard error,
and a drop that the unchanged system would produce every few hundred builds is
not evidence of anything. Below the attempt floor the gate falls back to the bare
tolerance rather than pretending a couple of samples have statistics — and above
it the allowance is capped, because at three attempts the arithmetic is wide
enough to excuse a total collapse, which is true and useless.

**Three buckets.** Correctness, trajectory, and cost fail separately (FR-020). A
change that improves accuracy at triple the price is a trade-off somebody should
decide on, and a single verdict cannot present it as one. It also means a cost
regression cannot be waved through by an accuracy improvement in the same run,
which is precisely the change most likely to arrive as a pair.

Every failure names the scenario and the axis. "The suite got worse" sends
somebody to read forty scenarios; SC-002 asks for the version that sends them to
one.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from config.constants.evaluation import (
    AXIS_COST,
    AXIS_TRAJECTORY,
    CORRECTNESS_AXES,
    DEFAULT_COST_TOLERANCE,
    DEFAULT_REGRESSION_TOLERANCE,
    DEFAULT_TRAJECTORY_TOLERANCE,
    MAX_FORGIVEN_DROP,
    MEASUREMENT_NOISE_FLOORS,
    MIN_ATTEMPTS_FOR_VARIANCE,
    VARIANCE_SIGMA_ALLOWANCE,
)
from tests.harness.regression.compare import AxisDelta, Comparison, MeasurementDelta

#: The three buckets a failure lands in.
CORRECTNESS_GATE = "correctness"
TRAJECTORY_GATE = "trajectory"
COST_GATE = "cost"

#: Which tracked numbers each measurement gate watches. Trajectory distance and
#: loop count say the route got worse; tokens and seconds say it got dearer.
TRAJECTORY_MEASUREMENTS: tuple[str, ...] = (
    "trajectory.distance",
    "trajectory.iterations",
    "trajectory.redundant_calls",
)
COST_MEASUREMENTS: tuple[str, ...] = ("cost.tokens", "cost.seconds")


def standard_error(rate: float, attempts: int) -> float:
    """Return how uncertain a pass rate measured over ``attempts`` is.

    Laplace-smoothed: one imagined pass and one imagined failure are added before
    the binomial standard error is taken. Without that, a rate of exactly zero or
    exactly one reports perfect certainty from a handful of samples, and the gate
    that trusts it fails the next honest run of an unchanged system.
    """
    if attempts <= 0:
        return 0.0
    smoothed = (rate * attempts + 1.0) / (attempts + 2.0)
    return math.sqrt(smoothed * (1.0 - smoothed) / attempts)


@dataclass(frozen=True, slots=True)
class GatePolicy:
    """How much movement each gate forgives, and how it accounts for noise."""

    correctness_tolerance: float = DEFAULT_REGRESSION_TOLERANCE
    trajectory_tolerance: float = DEFAULT_TRAJECTORY_TOLERANCE
    cost_tolerance: float = DEFAULT_COST_TOLERANCE
    sigma_allowance: float = VARIANCE_SIGMA_ALLOWANCE
    min_attempts_for_variance: int = MIN_ATTEMPTS_FOR_VARIANCE
    max_forgiven_drop: float = MAX_FORGIVEN_DROP
    correctness_axes: tuple[str, ...] = CORRECTNESS_AXES

    def allowed_drop(self, delta: AxisDelta, tolerance: float) -> float:
        """Return how far this axis may fall before it counts as a regression.

        The tolerance, widened by how uncertain both rates are, once there are
        enough attempts for that uncertainty to mean anything. Below the floor a
        spread computed from two samples is a number rather than a measurement,
        and treating it as one would let a gate be silenced by running the suite
        fewer times.

        The uncertainty is the *estimate's*, not the observed spread. A baseline
        that passed five times out of five has an observed standard deviation of
        zero and is not thereby certain: five successes at a true rate of 0.8
        happen a third of the time, and a gate that read that zero as certainty
        would fail the next honest run. So the rate is smoothed before its
        standard error is taken — one imagined pass and one imagined failure —
        which is what keeps a perfect baseline from becoming an impossible bar.
        """
        if delta.attempts < self.min_attempts_for_variance:
            return tolerance
        spread = math.hypot(
            standard_error(delta.baseline_rate, delta.baseline_attempts),
            standard_error(delta.current_rate, delta.current_attempts),
        )
        return min(tolerance + self.sigma_allowance * spread, self.max_forgiven_drop)

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this policy."""
        return {
            "correctness_tolerance": self.correctness_tolerance,
            "trajectory_tolerance": self.trajectory_tolerance,
            "cost_tolerance": self.cost_tolerance,
            "sigma_allowance": self.sigma_allowance,
            "min_attempts_for_variance": self.min_attempts_for_variance,
            "max_forgiven_drop": self.max_forgiven_drop,
            "correctness_axes": list(self.correctness_axes),
        }


@dataclass(frozen=True, slots=True)
class GateFailure:
    """One regression, named precisely enough to act on (SC-002)."""

    gate: str
    scenario: str
    axis: str
    detail: str
    delta: float = 0.0
    allowed: float = 0.0
    difficulty: int = 0

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this failure."""
        return {
            "gate": self.gate,
            "scenario": self.scenario,
            "axis": self.axis,
            "difficulty": self.difficulty,
            "detail": self.detail,
            "delta": round(self.delta, 4),
            "allowed": round(self.allowed, 4),
        }


@dataclass(frozen=True, slots=True)
class GateResult:
    """What the gate decided, split into the three buckets it decides in."""

    correctness: tuple[GateFailure, ...] = ()
    trajectory: tuple[GateFailure, ...] = ()
    cost: tuple[GateFailure, ...] = ()
    improvements: tuple[AxisDelta, ...] = ()
    baseline_label: str = ""
    current_label: str = ""
    policy: GatePolicy = field(default_factory=GatePolicy)
    corpus_matched: bool = True

    @property
    def failures(self) -> tuple[GateFailure, ...]:
        """Return every regression, in gate order."""
        return (*self.correctness, *self.trajectory, *self.cost)

    @property
    def passed(self) -> bool:
        """Return whether the build may go green."""
        return not self.failures

    @property
    def exit_code(self) -> int:
        """Return the process status a CI job should exit with."""
        return 0 if self.passed else 1

    def render(self) -> str:
        """Return the report a CI log shows, regressions first and named."""
        lines: list[str] = [
            f"measured against {self.baseline_label or 'an unnamed baseline'}"
            + (f", running {self.current_label}" if self.current_label else "")
        ]
        if not self.corpus_matched:
            lines.append(
                "  the corpora differed: this comparison was made deliberately across a "
                "corpus change and its deltas mix fixture edits with agent behaviour"
            )

        if self.passed:
            lines.append("no regression beyond tolerance")
        for gate, failures in (
            (CORRECTNESS_GATE, self.correctness),
            (TRAJECTORY_GATE, self.trajectory),
            (COST_GATE, self.cost),
        ):
            if not failures:
                continue
            lines.append("")
            lines.append(f"{gate.upper()} REGRESSION ({len(failures)})")
            for failure in failures:
                lines.append(f"  {failure.scenario} [{failure.axis}] {failure.detail}")

        if self.improvements:
            lines.append("")
            lines.append(f"improved on {len(self.improvements)} scenario-axis pairs")
        return "\n".join(lines)

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this decision."""
        return {
            "passed": self.passed,
            "baseline": self.baseline_label,
            "current": self.current_label,
            "corpus_matched": self.corpus_matched,
            "policy": self.policy.to_record(),
            "correctness": [failure.to_record() for failure in self.correctness],
            "trajectory": [failure.to_record() for failure in self.trajectory],
            "cost": [failure.to_record() for failure in self.cost],
            "improvements": [delta.to_record() for delta in self.improvements],
        }


def evaluate(comparison: Comparison, policy: GatePolicy | None = None) -> GateResult:
    """Return whether ``comparison`` clears the gate, and every reason it does not.

    Every regression is reported, not the first. A gate that stopped early would
    need one build per problem to find N of them, which on a suite this expensive
    is how a gate becomes something people run once a release.
    """
    rules = policy if policy is not None else GatePolicy()

    correctness: list[GateFailure] = []
    trajectory: list[GateFailure] = []
    improvements: list[AxisDelta] = []

    for delta in comparison.axis_deltas:
        if delta.delta > 0.0:
            improvements.append(delta)
            continue
        if delta.axis in rules.correctness_axes:
            failure = _axis_failure(delta, CORRECTNESS_GATE, rules, rules.correctness_tolerance)
            if failure is not None:
                correctness.append(failure)
        elif delta.axis == AXIS_TRAJECTORY:
            failure = _axis_failure(delta, TRAJECTORY_GATE, rules, rules.trajectory_tolerance)
            if failure is not None:
                trajectory.append(failure)

    cost: list[GateFailure] = []
    for measurement in comparison.measurement_deltas:
        if measurement.name in TRAJECTORY_MEASUREMENTS:
            failure = _measurement_failure(
                measurement, TRAJECTORY_GATE, AXIS_TRAJECTORY, rules.trajectory_tolerance
            )
            if failure is not None:
                trajectory.append(failure)
        elif measurement.name in COST_MEASUREMENTS:
            failure = _measurement_failure(measurement, COST_GATE, AXIS_COST, rules.cost_tolerance)
            if failure is not None:
                cost.append(failure)

    return GateResult(
        correctness=tuple(correctness),
        trajectory=tuple(trajectory),
        cost=tuple(cost),
        improvements=tuple(improvements),
        baseline_label=comparison.baseline_label,
        current_label=comparison.current_label,
        policy=rules,
        corpus_matched=comparison.corpus_matched,
    )


def _axis_failure(
    delta: AxisDelta, gate: str, policy: GatePolicy, tolerance: float
) -> GateFailure | None:
    """Return the failure this drop amounts to, or ``None`` when it is inside tolerance."""
    allowed = policy.allowed_drop(delta, tolerance)
    drop = -delta.delta
    if drop <= allowed:
        return None
    return GateFailure(
        gate=gate,
        scenario=delta.scenario,
        axis=delta.axis,
        difficulty=delta.difficulty,
        delta=delta.delta,
        allowed=allowed,
        detail=(
            f"{delta.baseline_rate:.0%} then {delta.current_rate:.0%} ({delta.delta:+.0%}), "
            f"beyond an allowance of {allowed:.0%} over {delta.attempts} attempts"
        ),
    )


def _measurement_failure(
    measurement: MeasurementDelta, gate: str, axis: str, tolerance: float
) -> GateFailure | None:
    """Return the failure this rise amounts to, or ``None`` when it is inside tolerance.

    Two hurdles, and the absolute one is the important half here. A percentage on
    a tiny base is not a measurement: an offline scenario that took thirty
    milliseconds and then forty-two has risen by forty per cent and by nothing,
    and a gate that reported it would be red every other build over something
    nobody can fix.
    """
    floor = MEASUREMENT_NOISE_FLOORS.get(measurement.name, 0.0)
    if measurement.ratio <= tolerance or measurement.delta < floor:
        return None
    name = measurement.name.split(".", 1)[-1]
    return GateFailure(
        gate=gate,
        scenario=measurement.scenario,
        axis=axis,
        difficulty=measurement.difficulty,
        delta=measurement.ratio,
        allowed=tolerance,
        detail=(
            f"{name} rose from {measurement.baseline_mean:.0f} to "
            f"{measurement.current_mean:.0f} ({measurement.ratio:+.0%}), beyond "
            f"an allowance of {tolerance:.0%}"
        ),
    )


def failures_by_scenario(result: GateResult) -> Mapping[str, tuple[GateFailure, ...]]:
    """Return every failure grouped by the scenario it happened on."""
    grouped: dict[str, list[GateFailure]] = {}
    for failure in result.failures:
        grouped.setdefault(failure.scenario, []).append(failure)
    return {key: tuple(found) for key, found in grouped.items()}


def named_axes(failures: Sequence[GateFailure]) -> tuple[str, ...]:
    """Return the axes ``failures`` name, deduplicated in order."""
    seen: dict[str, None] = {}
    for failure in failures:
        seen.setdefault(failure.axis, None)
    return tuple(seen)


__all__ = [
    "COST_GATE",
    "COST_MEASUREMENTS",
    "CORRECTNESS_GATE",
    "TRAJECTORY_GATE",
    "TRAJECTORY_MEASUREMENTS",
    "GateFailure",
    "GatePolicy",
    "GateResult",
    "evaluate",
    "failures_by_scenario",
    "named_axes",
]
