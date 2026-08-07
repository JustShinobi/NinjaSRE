"""What each mechanism was worth, per axis and per difficulty, sign included.

A contribution is a subtraction: the baseline's rate minus the rate the arm
without the mechanism achieved. Positive means the mechanism helped. That
convention is stated once, here, and every number in the report obeys it, because
a table where half the columns are "improvement" and half are "difference" is a
table people misread once and stop trusting afterwards.

Three things this report refuses to do.

**It will not price an arm that did not run.** A mechanism whose arm failed
appears in ``unmeasured`` and nowhere else. Reporting it as "no measurable
effect" would be the most damaging thing the harness could do: a broken
experiment and a null result look identical in a table and mean opposite things.

**It will not dress noise as a finding.** A difference inside the noise floor is
reported as no measurable effect rather than as a number with two decimal places.

**It will not bury a harmful mechanism.** A negative contribution is flagged
above the table, not in a footnote. Discovering that a mechanism degrades level-4
scenarios is exactly what Article VII exists to surface, and the response is to
fix or disable it — not to print it in the same grey as everything else.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from config.constants.evaluation import (
    ABLATION_NOISE_FLOOR,
    SCENARIO_DIFFICULTY_DESCRIPTIONS,
    SCORING_AXES,
)
from tests.harness.ablation.runner import AblationResult, ArmResult
from tests.harness.scoring.report import ScenarioStatistic, SuiteScore


@dataclass(frozen=True, slots=True)
class Contribution:
    """What one mechanism was worth on one axis, at one level or across the corpus."""

    mechanism: str
    arm: str
    axis: str
    baseline_rate: float
    ablated_rate: float
    baseline_stdev: float = 0.0
    ablated_stdev: float = 0.0
    difficulty: int | None = None
    attempts: int = 0

    @property
    def delta(self) -> float:
        """Return what the mechanism added. Positive means it helped."""
        return self.baseline_rate - self.ablated_rate

    @property
    def measurable(self) -> bool:
        """Return whether the difference is bigger than the noise floor."""
        return abs(self.delta) >= ABLATION_NOISE_FLOOR

    @property
    def harmful(self) -> bool:
        """Return whether removing the mechanism made results *better* (FR-015)."""
        return self.measurable and self.delta < 0.0

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this contribution."""
        return {
            "mechanism": self.mechanism,
            "arm": self.arm,
            "axis": self.axis,
            "difficulty": self.difficulty,
            "baseline_rate": round(self.baseline_rate, 4),
            "ablated_rate": round(self.ablated_rate, 4),
            "baseline_stdev": round(self.baseline_stdev, 4),
            "ablated_stdev": round(self.ablated_stdev, 4),
            "delta": round(self.delta, 4),
            "measurable": self.measurable,
            "harmful": self.harmful,
            "attempts": self.attempts,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> Contribution:
        """Return the contribution a stored record describes."""
        level = record.get("difficulty")
        return cls(
            mechanism=str(record["mechanism"]),
            arm=str(record.get("arm", "")),
            axis=str(record["axis"]),
            baseline_rate=float(record.get("baseline_rate", 0.0)),
            ablated_rate=float(record.get("ablated_rate", 0.0)),
            baseline_stdev=float(record.get("baseline_stdev", 0.0)),
            ablated_stdev=float(record.get("ablated_stdev", 0.0)),
            difficulty=None if level is None else int(level),
            attempts=int(record.get("attempts", 0)),
        )


@dataclass(frozen=True, slots=True)
class AblationReport:
    """Every mechanism priced, and the ones nobody could price."""

    contributions: tuple[Contribution, ...] = ()
    unmeasured: tuple[str, ...] = ()
    corpus_version: str = ""
    attempts_per_scenario: int = 0
    arms: tuple[str, ...] = ()

    def for_mechanism(self, name: str) -> tuple[Contribution, ...]:
        """Return everything measured about the mechanism called ``name``."""
        return tuple(found for found in self.contributions if found.mechanism == name)

    @property
    def harmful(self) -> tuple[Contribution, ...]:
        """Return every corpus-wide contribution whose mechanism is making things worse."""
        return tuple(
            found for found in self.contributions if found.harmful and found.difficulty is None
        )

    @property
    def mechanisms(self) -> tuple[str, ...]:
        """Return every mechanism this report priced, in first-appearance order."""
        seen: dict[str, None] = {}
        for found in self.contributions:
            seen.setdefault(found.mechanism, None)
        return tuple(seen)

    def render(self) -> str:
        """Return the report a person reads before a release.

        Harm first, deliberately. A negative contribution at the bottom of a
        forty-row table is a negative contribution nobody acts on.
        """
        lines: list[str] = []

        if self.harmful:
            lines.append("HARMFUL MECHANISMS — removing these improved the score")
            for found in self.harmful:
                lines.append(
                    f"  {found.mechanism} on {found.axis}: "
                    f"{found.ablated_rate:.0%} without it against {found.baseline_rate:.0%} "
                    f"with it ({found.delta:+.0%})"
                )
            lines.append("")

        if self.unmeasured:
            lines.append(
                "NOT MEASURED — these arms did not complete, so nothing is claimed about them:"
            )
            for name in self.unmeasured:
                lines.append(f"  {name}")
            lines.append("")

        lines.append(f"contribution per mechanism, per axis (corpus {self.corpus_version})")
        lines.append(f"{'mechanism':<22}{'axis':<14}{'with':<9}{'without':<10}delta")
        for mechanism in self.mechanisms:
            for found in self.for_mechanism(mechanism):
                if found.difficulty is not None:
                    continue
                delta = f"{found.delta:+.0%}" if found.measurable else "no measurable effect"
                lines.append(
                    f"{found.mechanism:<22}{found.axis:<14}"
                    f"{found.baseline_rate:<9.0%}{found.ablated_rate:<10.0%}{delta}"
                )

        lines.append("")
        lines.append("by difficulty")
        for mechanism in self.mechanisms:
            for found in self.for_mechanism(mechanism):
                if found.difficulty is None or not found.measurable:
                    continue
                lines.append(
                    f"  {found.mechanism} on {found.axis}, level {found.difficulty} "
                    f"({SCENARIO_DIFFICULTY_DESCRIPTIONS.get(found.difficulty, '')}): "
                    f"{found.delta:+.0%}"
                )
        return "\n".join(lines)

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this report."""
        return {
            "corpus_version": self.corpus_version,
            "attempts_per_scenario": self.attempts_per_scenario,
            "arms": list(self.arms),
            "unmeasured": list(self.unmeasured),
            "harmful": [found.to_record() for found in self.harmful],
            "contributions": [found.to_record() for found in self.contributions],
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> AblationReport:
        """Return the report a stored record describes."""
        return cls(
            contributions=tuple(
                Contribution.from_record(item) for item in record.get("contributions") or ()
            ),
            unmeasured=tuple(str(item) for item in record.get("unmeasured") or ()),
            corpus_version=str(record.get("corpus_version", "")),
            attempts_per_scenario=int(record.get("attempts_per_scenario", 0)),
            arms=tuple(str(item) for item in record.get("arms") or ()),
        )


def report_for(result: AblationResult) -> AblationReport:
    """Return ``result`` as a contribution per mechanism, per axis, per level."""
    baseline = result.baseline
    contributions: list[Contribution] = []
    unmeasured: list[str] = []

    for arm in result.arms:
        if arm.config.is_baseline:
            continue
        if not arm.completed:
            unmeasured.extend(arm.config.disabled)
            continue
        contributions.extend(_contributions(baseline, arm))

    return AblationReport(
        contributions=tuple(contributions),
        unmeasured=tuple(dict.fromkeys(unmeasured)),
        corpus_version=result.corpus_version,
        attempts_per_scenario=result.attempts_per_scenario,
        arms=tuple(found.config.name for found in result.arms),
    )


def _contributions(baseline: ArmResult, arm: ArmResult) -> list[Contribution]:
    """Return one contribution per axis, plus one per axis per difficulty level."""
    label = arm.mechanism_label
    found: list[Contribution] = []

    for axis in SCORING_AXES:
        with_it = baseline.suite.axis(axis)
        without_it = arm.suite.axis(axis)
        if with_it is None or without_it is None or not with_it.asserted:
            continue
        found.append(
            Contribution(
                mechanism=label,
                arm=arm.config.name,
                axis=axis,
                baseline_rate=with_it.pass_rate,
                ablated_rate=without_it.pass_rate,
                baseline_stdev=with_it.stdev,
                ablated_stdev=without_it.stdev,
                attempts=without_it.attempts,
            )
        )

    for level in sorted(_levels(baseline.suite) | _levels(arm.suite)):
        for axis in SCORING_AXES:
            with_it = _level_axis(baseline.suite, level, axis)
            without_it = _level_axis(arm.suite, level, axis)
            if with_it is None or without_it is None:
                continue
            attempts, passes = with_it
            ablated_attempts, ablated_passes = without_it
            if not attempts or not ablated_attempts:
                continue
            found.append(
                Contribution(
                    mechanism=label,
                    arm=arm.config.name,
                    axis=axis,
                    difficulty=level,
                    baseline_rate=passes / attempts,
                    ablated_rate=ablated_passes / ablated_attempts,
                    attempts=ablated_attempts,
                )
            )
    return found


def _levels(suite: SuiteScore) -> set[int]:
    """Return every curriculum level this run covered."""
    return {found.difficulty for found in suite.scenarios}


def _level_axis(suite: SuiteScore, level: int, axis: str) -> tuple[int, int] | None:
    """Return attempts and passes for one axis at one level, or ``None`` for neither."""
    members: Sequence[ScenarioStatistic] = [
        found for found in suite.scenarios if found.difficulty == level
    ]
    if not members:
        return None
    attempts = 0
    passes = 0
    for found in members:
        statistic = found.axis(axis)
        if statistic is None:
            continue
        attempts += statistic.attempts
        passes += statistic.passes
    return (attempts, passes)


__all__ = ["AblationReport", "Contribution", "report_for"]
