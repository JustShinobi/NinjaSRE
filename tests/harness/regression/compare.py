"""Two runs, subtracted, per scenario and per axis — and refusing when they are not comparable.

The refusal is the part worth explaining. A corpus that gained a scenario, lost
one, or renamed one produces a suite result whose numbers are not on the same
scale as the previous one's, and subtracting them anyway yields a delta that looks
exactly like an agent regression. The plan lists that as a risk and its mitigation
as "a corpus change requires a new baseline"; this is where that becomes
mechanical rather than a convention.

``strict_corpus=False`` exists because refusing by default is not refusing at all
if there is no way to look. A deliberate cross-corpus comparison reports which
scenarios appeared and which vanished, and says on its face that the corpora
differed — so a number lifted out of it carries that with it.

Deltas are signed from the *current* run's point of view: negative is worse.
Stated once, obeyed everywhere. A table where half the columns mean improvement
and half mean difference is a table people misread once and stop trusting.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from config.constants.evaluation import SCORING_AXES
from tests.harness.scoring.report import (
    TRACKED_MEASUREMENTS,
    ScenarioStatistic,
    SuiteScore,
)


class CorpusMismatch(ValueError):
    """Two suite runs covered different scenarios, so subtracting them measures nothing."""


@dataclass(frozen=True, slots=True)
class AxisDelta:
    """How one axis moved on one scenario between two runs."""

    scenario: str
    axis: str
    baseline_rate: float
    current_rate: float
    baseline_stdev: float = 0.0
    current_stdev: float = 0.0
    baseline_attempts: int = 0
    current_attempts: int = 0
    difficulty: int = 0

    @property
    def delta(self) -> float:
        """Return the movement. Negative is worse."""
        return self.current_rate - self.baseline_rate

    @property
    def regressed(self) -> bool:
        """Return whether this axis moved down at all, before any tolerance is applied."""
        return self.delta < 0.0

    @property
    def attempts(self) -> int:
        """Return the smaller of the two attempt counts, which bounds what can be said."""
        return min(self.baseline_attempts, self.current_attempts)

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this delta."""
        return {
            "scenario": self.scenario,
            "axis": self.axis,
            "difficulty": self.difficulty,
            "baseline_rate": round(self.baseline_rate, 4),
            "current_rate": round(self.current_rate, 4),
            "baseline_stdev": round(self.baseline_stdev, 4),
            "current_stdev": round(self.current_stdev, 4),
            "delta": round(self.delta, 4),
            "attempts": self.attempts,
        }


@dataclass(frozen=True, slots=True)
class MeasurementDelta:
    """How one tracked number moved on one scenario between two runs."""

    scenario: str
    name: str
    baseline_mean: float
    current_mean: float
    baseline_stdev: float = 0.0
    difficulty: int = 0

    @property
    def delta(self) -> float:
        """Return the movement. Positive is worse: these are all costs."""
        return self.current_mean - self.baseline_mean

    @property
    def ratio(self) -> float:
        """Return the movement as a share of the baseline, or zero from nothing.

        A share rather than an absolute, because "four hundred more tokens" means
        something different against four thousand than against forty thousand, and
        one tolerance has to cover both.
        """
        return self.delta / self.baseline_mean if self.baseline_mean else 0.0

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this delta."""
        return {
            "scenario": self.scenario,
            "measurement": self.name,
            "difficulty": self.difficulty,
            "baseline_mean": round(self.baseline_mean, 4),
            "current_mean": round(self.current_mean, 4),
            "baseline_stdev": round(self.baseline_stdev, 4),
            "delta": round(self.delta, 4),
            "ratio": round(self.ratio, 4),
        }


@dataclass(frozen=True, slots=True)
class Comparison:
    """Every per-scenario, per-axis movement between two runs (FR-017)."""

    baseline_label: str = ""
    current_label: str = ""
    baseline_corpus: str = ""
    current_corpus: str = ""
    axis_deltas: tuple[AxisDelta, ...] = ()
    measurement_deltas: tuple[MeasurementDelta, ...] = ()
    missing_scenarios: tuple[str, ...] = ()
    new_scenarios: tuple[str, ...] = ()

    @property
    def corpus_matched(self) -> bool:
        """Return whether both runs covered the same corpus."""
        return not self.missing_scenarios and not self.new_scenarios

    def for_scenario(self, key: str) -> tuple[AxisDelta, ...]:
        """Return every axis movement on one scenario."""
        return tuple(delta for delta in self.axis_deltas if delta.scenario == key)

    def measurements_for(self, key: str) -> tuple[MeasurementDelta, ...]:
        """Return every tracked-number movement on one scenario."""
        return tuple(delta for delta in self.measurement_deltas if delta.scenario == key)

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this comparison."""
        return {
            "baseline": self.baseline_label,
            "current": self.current_label,
            "baseline_corpus": self.baseline_corpus,
            "current_corpus": self.current_corpus,
            "corpus_matched": self.corpus_matched,
            "missing_scenarios": list(self.missing_scenarios),
            "new_scenarios": list(self.new_scenarios),
            "axis_deltas": [delta.to_record() for delta in self.axis_deltas],
            "measurement_deltas": [delta.to_record() for delta in self.measurement_deltas],
        }


def compare(baseline: SuiteScore, current: SuiteScore, *, strict_corpus: bool = True) -> Comparison:
    """Return the per-scenario, per-axis delta between two suite runs.

    Raises:
        CorpusMismatch: the two runs covered different scenarios and
            ``strict_corpus`` is set — which is the default, because a corpus
            change and an agent regression look identical in a pass rate.
    """
    before = {found.key: found for found in baseline.scenarios}
    after = {found.key: found for found in current.scenarios}

    missing = tuple(sorted(set(before) - set(after)))
    added = tuple(sorted(set(after) - set(before)))

    if strict_corpus and (missing or added):
        raise CorpusMismatch(
            f"these two runs covered different corpora — {list(missing)} vanished and "
            f"{list(added)} appeared. A corpus change requires a new baseline: subtracting "
            f"across one reports a fixture edit as an agent regression, which is the most "
            f"expensive wrong conclusion this gate can reach. Compare with "
            f"strict_corpus=False to look anyway."
        )

    axis_deltas: list[AxisDelta] = []
    measurement_deltas: list[MeasurementDelta] = []
    for key in sorted(set(before) & set(after)):
        axis_deltas.extend(_axis_deltas(key, before[key], after[key]))
        measurement_deltas.extend(_measurement_deltas(key, before[key], after[key]))

    return Comparison(
        baseline_label=baseline.label,
        current_label=current.label,
        baseline_corpus=baseline.corpus_version,
        current_corpus=current.corpus_version,
        axis_deltas=tuple(axis_deltas),
        measurement_deltas=tuple(measurement_deltas),
        missing_scenarios=missing,
        new_scenarios=added,
    )


def _axis_deltas(key: str, before: ScenarioStatistic, after: ScenarioStatistic) -> list[AxisDelta]:
    """Return one delta per axis both runs asserted on this scenario."""
    found: list[AxisDelta] = []
    for axis in SCORING_AXES:
        was = before.axis(axis)
        now = after.axis(axis)
        if was is None or now is None or not was.asserted or not now.asserted:
            continue
        found.append(
            AxisDelta(
                scenario=key,
                axis=axis,
                baseline_rate=was.pass_rate,
                current_rate=now.pass_rate,
                baseline_stdev=was.stdev,
                current_stdev=now.stdev,
                baseline_attempts=was.attempts,
                current_attempts=now.attempts,
                difficulty=after.difficulty,
            )
        )
    return found


def _measurement_deltas(
    key: str, before: ScenarioStatistic, after: ScenarioStatistic
) -> list[MeasurementDelta]:
    """Return one delta per tracked number both runs recorded on this scenario."""
    found: list[MeasurementDelta] = []
    for axis, name in TRACKED_MEASUREMENTS:
        label = f"{axis}.{name}"
        was = before.measurement(label)
        now = after.measurement(label)
        if was is None or now is None or not was.samples or not now.samples:
            continue
        found.append(
            MeasurementDelta(
                scenario=key,
                name=label,
                baseline_mean=was.mean,
                current_mean=now.mean,
                baseline_stdev=was.stdev,
                difficulty=after.difficulty,
            )
        )
    return found


def render(comparison: Comparison, *, deltas: Sequence[AxisDelta] = ()) -> str:
    """Return a readable listing of ``deltas``, or of everything that moved."""
    moved = deltas or tuple(delta for delta in comparison.axis_deltas if delta.delta)
    if not moved:
        return "nothing moved"
    lines = [f"{'scenario':<30}{'axis':<14}{'before':<10}{'after':<10}delta"]
    for delta in moved:
        lines.append(
            f"{delta.scenario:<30}{delta.axis:<14}"
            f"{delta.baseline_rate:<10.0%}{delta.current_rate:<10.0%}{delta.delta:+.0%}"
        )
    return "\n".join(lines)


def deltas_by_axis(comparison: Comparison) -> Mapping[str, tuple[AxisDelta, ...]]:
    """Return the movements grouped by axis, for a gate that buckets them."""
    grouped: dict[str, list[AxisDelta]] = {axis: [] for axis in SCORING_AXES}
    for delta in comparison.axis_deltas:
        grouped.setdefault(delta.axis, []).append(delta)
    return {axis: tuple(found) for axis, found in grouped.items()}


__all__ = [
    "AxisDelta",
    "Comparison",
    "CorpusMismatch",
    "MeasurementDelta",
    "compare",
    "deltas_by_axis",
    "render",
]
