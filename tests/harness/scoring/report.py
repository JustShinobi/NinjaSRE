"""Many attempts, aggregated, with the spread that makes the mean mean something.

A suite result is a mean, and a mean on its own is the number that turns a
regression gate into a flaky one. Four passes in five is not "eighty percent" in
the way a single run is eighty percent of anything: it is a scenario the agent
solves *usually*, and the release that turns it into five in five has done
something the release that turns it into three in five has undone. Report only
the mean and those two look identical, the gate fires on noise, somebody widens
the tolerance, and the gate stops gating.

So every rate here carries its standard deviation, and every measurement — edit
distance, tokens, seconds, loop count — carries a mean and a spread too. The
regression gate downstream subtracts these; the ablation report divides them.
Both need a number and an error bar, and neither can invent the error bar later.

Two renderings, one report. ``render`` is what a person reads at the end of a
run; ``to_record`` is what a baseline stores and a CI job publishes, and it round
trips, because a baseline that could be written and not read back is a
screenshot.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from config.constants.evaluation import (
    SCENARIO_DIFFICULTY_DESCRIPTIONS,
    SCORING_AXES,
)
from tests.harness.scoring.composite import ScenarioScore

#: The per-axis measurements a suite tracks over time. Not everything an axis
#: records: these are the ones a trend is drawn from and a gate compares, and a
#: report that averaged every number an axis happened to emit would bury them.
TRACKED_MEASUREMENTS: tuple[tuple[str, str], ...] = (
    ("trajectory", "distance"),
    ("trajectory", "extra_actions"),
    ("trajectory", "redundant_calls"),
    ("trajectory", "iterations"),
    ("cost", "tokens"),
    ("cost", "seconds"),
)


def _rate(passes: int, attempts: int) -> float:
    """Return the share of ``attempts`` that passed, or zero for none."""
    return passes / attempts if attempts else 0.0


@dataclass(frozen=True, slots=True)
class Measurement:
    """One number tracked across attempts, with its spread."""

    name: str
    mean: float = 0.0
    stdev: float = 0.0
    samples: int = 0

    @classmethod
    def of(cls, name: str, values: Sequence[float]) -> Measurement:
        """Return the statistics of ``values``.

        Population standard deviation, not sample: these are every attempt that
        was made, not a sample drawn from a larger population of attempts that
        might have been.
        """
        if not values:
            return cls(name=name)
        return cls(
            name=name,
            mean=statistics.fmean(values),
            stdev=statistics.pstdev(values) if len(values) > 1 else 0.0,
            samples=len(values),
        )

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this measurement."""
        return {
            "name": self.name,
            "mean": round(self.mean, 4),
            "stdev": round(self.stdev, 4),
            "samples": self.samples,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> Measurement:
        """Return the measurement a stored record describes."""
        return cls(
            name=str(record["name"]),
            mean=float(record.get("mean", 0.0)),
            stdev=float(record.get("stdev", 0.0)),
            samples=int(record.get("samples", 0)),
        )


@dataclass(frozen=True, slots=True)
class AxisStatistic:
    """One axis across every attempt that asserted it."""

    axis: str
    attempts: int = 0
    passes: int = 0
    stdev: float = 0.0

    @property
    def pass_rate(self) -> float:
        """Return the share of asserting attempts that passed."""
        return _rate(self.passes, self.attempts)

    @property
    def asserted(self) -> bool:
        """Return whether any attempt asserted this axis at all."""
        return self.attempts > 0

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this axis."""
        return {
            "axis": self.axis,
            "attempts": self.attempts,
            "passes": self.passes,
            "pass_rate": round(self.pass_rate, 4),
            "stdev": round(self.stdev, 4),
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> AxisStatistic:
        """Return the axis statistic a stored record describes."""
        return cls(
            axis=str(record["axis"]),
            attempts=int(record.get("attempts", 0)),
            passes=int(record.get("passes", 0)),
            stdev=float(record.get("stdev", 0.0)),
        )


@dataclass(frozen=True, slots=True)
class ScenarioStatistic:
    """One scenario across every attempt made at it."""

    key: str
    suite: str = ""
    scenario_id: str = ""
    difficulty: int = 0
    failure_mode: str = ""
    attempts: int = 0
    passes: int = 0
    pass_stdev: float = 0.0
    axes: tuple[AxisStatistic, ...] = ()
    measurements: tuple[Measurement, ...] = ()
    deviations: int = 0
    different_valid_routes: int = 0
    failed_axes: tuple[str, ...] = ()

    @property
    def pass_rate(self) -> float:
        """Return the share of attempts that passed every axis they asserted."""
        return _rate(self.passes, self.attempts)

    @property
    def permanently_unsolved(self) -> bool:
        """Return whether nothing ever solved this scenario."""
        return self.attempts > 0 and self.passes == 0

    def axis(self, name: str) -> AxisStatistic | None:
        """Return the statistic for the axis called ``name``, or ``None``."""
        return next((found for found in self.axes if found.axis == name), None)

    def measurement(self, name: str) -> Measurement | None:
        """Return the tracked measurement called ``name``, or ``None``."""
        return next((found for found in self.measurements if found.name == name), None)

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this scenario."""
        return {
            "key": self.key,
            "suite": self.suite,
            "scenario": self.scenario_id,
            "difficulty": self.difficulty,
            "failure_mode": self.failure_mode,
            "attempts": self.attempts,
            "passes": self.passes,
            "pass_rate": round(self.pass_rate, 4),
            "pass_stdev": round(self.pass_stdev, 4),
            "deviations": self.deviations,
            "different_valid_routes": self.different_valid_routes,
            "failed_axes": list(self.failed_axes),
            "axes": [axis.to_record() for axis in self.axes],
            "measurements": [found.to_record() for found in self.measurements],
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> ScenarioStatistic:
        """Return the scenario statistic a stored record describes."""
        return cls(
            key=str(record["key"]),
            suite=str(record.get("suite", "")),
            scenario_id=str(record.get("scenario", "")),
            difficulty=int(record.get("difficulty", 0)),
            failure_mode=str(record.get("failure_mode", "")),
            attempts=int(record.get("attempts", 0)),
            passes=int(record.get("passes", 0)),
            pass_stdev=float(record.get("pass_stdev", 0.0)),
            deviations=int(record.get("deviations", 0)),
            different_valid_routes=int(record.get("different_valid_routes", 0)),
            failed_axes=tuple(str(item) for item in record.get("failed_axes") or ()),
            axes=tuple(AxisStatistic.from_record(item) for item in record.get("axes") or ()),
            measurements=tuple(
                Measurement.from_record(item) for item in record.get("measurements") or ()
            ),
        )


@dataclass(frozen=True, slots=True)
class GroupStatistic:
    """One stratum of the corpus — a difficulty level, or a failure mode."""

    name: str
    attempts: int = 0
    passes: int = 0
    difficulty: int = 0
    description: str = ""
    scenarios: tuple[str, ...] = ()

    @property
    def pass_rate(self) -> float:
        """Return this stratum's pass rate."""
        return _rate(self.passes, self.attempts)


@dataclass(frozen=True, slots=True)
class SuiteScore:
    """What one suite run says, at every granularity anybody asks for it at."""

    scenarios: tuple[ScenarioStatistic, ...] = ()
    label: str = ""
    corpus_version: str = ""
    duration_seconds: float = 0.0
    attempts_per_scenario: int = 0
    axes: tuple[AxisStatistic, ...] = field(default=())

    @property
    def attempts(self) -> int:
        """Return how many attempts the run made in total."""
        return sum(found.attempts for found in self.scenarios)

    @property
    def passes(self) -> int:
        """Return how many attempts passed every axis they asserted."""
        return sum(found.passes for found in self.scenarios)

    @property
    def pass_rate(self) -> float:
        """Return the whole run's pass rate."""
        return _rate(self.passes, self.attempts)

    def axis_rate(self, name: str) -> float:
        """Return the pass rate of one axis across every attempt that asserted it."""
        found = next((axis for axis in self.axes if axis.axis == name), None)
        return found.pass_rate if found is not None else 0.0

    def axis(self, name: str) -> AxisStatistic | None:
        """Return the corpus-wide statistic for one axis, or ``None``."""
        return next((axis for axis in self.axes if axis.axis == name), None)

    def scenario(self, key: str) -> ScenarioStatistic | None:
        """Return one scenario's statistic, or ``None`` when it did not run."""
        return next((found for found in self.scenarios if found.key == key), None)

    def by_difficulty(self) -> tuple[GroupStatistic, ...]:
        """Return one group per curriculum level present, easiest first.

        The stratification that separates an improvement which helped everywhere
        from one that helped on the easy cases — and only the first is a
        capability change.
        """
        return _group(
            self.scenarios,
            key=lambda found: str(found.difficulty),
            difficulty=lambda found: found.difficulty,
            description=lambda found: SCENARIO_DIFFICULTY_DESCRIPTIONS.get(found.difficulty, ""),
            order=lambda group: (group.difficulty, group.name),
        )

    def by_failure_mode(self) -> tuple[GroupStatistic, ...]:
        """Return one group per failure mode present, in name order.

        "The agent gets memory pressure right and connection pools wrong" is the
        sentence this makes sayable, and one accuracy number never can.
        """
        return _group(
            self.scenarios,
            key=lambda found: found.failure_mode,
            difficulty=lambda _: 0,
            description=lambda _: "",
            order=lambda group: (0, group.name),
        )

    def failures_by_axis(self) -> dict[str, int]:
        """Return how many attempts each axis failed, across the corpus.

        Failure-mode analysis in the sense the plan means it: "two failures" is
        not a finding, and "two accuracy failures and no cost failures" is.
        """
        counted = dict.fromkeys(SCORING_AXES, 0)
        for found in self.scenarios:
            for axis in found.axes:
                counted[axis.axis] = counted.get(axis.axis, 0) + (axis.attempts - axis.passes)
        return counted

    @property
    def permanently_unsolved(self) -> tuple[ScenarioStatistic, ...]:
        """Return the scenarios nothing solved, which are candidates for retirement."""
        return tuple(found for found in self.scenarios if found.permanently_unsolved)

    @property
    def different_valid_routes(self) -> tuple[ScenarioStatistic, ...]:
        """Return the scenarios that were solved by a route the answer key does not name."""
        return tuple(found for found in self.scenarios if found.different_valid_routes)

    def render(self) -> str:
        """Return the report a person reads at the end of a run."""
        lines: list[str] = []
        if self.label:
            lines.append(f"{self.label}")
        lines.append(
            f"{self.passes}/{self.attempts} attempts passed ({self.pass_rate:.0%})"
            + (f" in {self.duration_seconds:.1f}s" if self.duration_seconds else "")
        )
        if self.corpus_version:
            lines.append(f"corpus {self.corpus_version}")

        lines.append("")
        lines.append(f"{'axis':<14}{'pass rate':<12}{'attempts':<10}spread")
        for axis in self.axes:
            if not axis.asserted:
                lines.append(f"{axis.axis:<14}{'—':<12}{'0':<10}not asserted by any answer key")
                continue
            lines.append(
                f"{axis.axis:<14}{axis.pass_rate:<12.0%}{axis.attempts:<10}±{axis.stdev:.2f}"
            )

        lines.append("")
        lines.append(f"{'level':<7}{'pass rate':<12}{'attempts':<10}definition")
        for level in self.by_difficulty():
            lines.append(
                f"{level.difficulty:<7}{level.pass_rate:<12.0%}{level.attempts:<10}"
                f"{level.description}"
            )

        lines.append("")
        for found in self.scenarios:
            mark = "ok  " if found.passes == found.attempts else "FAIL"
            detail = ", ".join(found.failed_axes) if found.failed_axes else ""
            lines.append(
                f"  {mark} [{found.difficulty}] {found.key:<44}"
                f"{found.passes}/{found.attempts:<6}±{found.pass_stdev:.2f}  {detail}"
            )

        for found in self.different_valid_routes:
            lines.append(
                f"  deviation: {found.key} reached the right answer by a route the key "
                f"does not name"
            )
        return "\n".join(lines)

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this run."""
        return {
            "label": self.label,
            "corpus_version": self.corpus_version,
            "attempts": self.attempts,
            "passes": self.passes,
            "pass_rate": round(self.pass_rate, 4),
            "attempts_per_scenario": self.attempts_per_scenario,
            "duration_seconds": round(self.duration_seconds, 3),
            "axes": [axis.to_record() for axis in self.axes],
            "by_difficulty": [
                {
                    "difficulty": level.difficulty,
                    "description": level.description,
                    "attempts": level.attempts,
                    "passes": level.passes,
                    "pass_rate": round(level.pass_rate, 4),
                }
                for level in self.by_difficulty()
            ],
            "by_failure_mode": [
                {
                    "failure_mode": mode.name,
                    "attempts": mode.attempts,
                    "passes": mode.passes,
                    "pass_rate": round(mode.pass_rate, 4),
                }
                for mode in self.by_failure_mode()
            ],
            "failures_by_axis": self.failures_by_axis(),
            "scenarios": [found.to_record() for found in self.scenarios],
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> SuiteScore:
        """Return the run a stored record describes.

        The strata are recomputed from the scenarios rather than read back. They
        are derived, and a hand-edited record claiming a level-4 pass rate its
        own scenarios do not support is exactly what a baseline must not be able
        to do.
        """
        return cls(
            scenarios=tuple(
                ScenarioStatistic.from_record(item) for item in record.get("scenarios") or ()
            ),
            label=str(record.get("label", "")),
            corpus_version=str(record.get("corpus_version", "")),
            duration_seconds=float(record.get("duration_seconds", 0.0)),
            attempts_per_scenario=int(record.get("attempts_per_scenario", 0)),
            axes=tuple(AxisStatistic.from_record(item) for item in record.get("axes") or ()),
        )


def summarise(
    scores: Sequence[ScenarioScore],
    *,
    label: str = "",
    corpus_version: str = "",
    duration_seconds: float = 0.0,
) -> SuiteScore:
    """Return ``scores`` aggregated per scenario and per axis, with variance."""
    per_scenario: dict[str, list[ScenarioScore]] = {}
    for score in scores:
        per_scenario.setdefault(score.key, []).append(score)

    scenarios = tuple(_scenario_statistic(key, attempts) for key, attempts in per_scenario.items())
    ordered = tuple(sorted(scenarios, key=lambda found: (found.difficulty, found.key)))
    attempts_each = max((found.attempts for found in ordered), default=0)

    return SuiteScore(
        scenarios=ordered,
        label=label,
        corpus_version=corpus_version,
        duration_seconds=duration_seconds,
        attempts_per_scenario=attempts_each,
        axes=_corpus_axes(scores),
    )


def _scenario_statistic(key: str, attempts: Sequence[ScenarioScore]) -> ScenarioStatistic:
    """Return the statistics of every attempt at one scenario."""
    first = attempts[0]
    outcomes = [1.0 if score.passed else 0.0 for score in attempts]
    failed: list[str] = []
    for score in attempts:
        failed.extend(axis for axis in score.failed_axes if axis not in failed)

    return ScenarioStatistic(
        key=key,
        suite=first.suite,
        scenario_id=first.scenario_id,
        difficulty=first.difficulty,
        failure_mode=first.failure_mode,
        attempts=len(attempts),
        passes=int(sum(outcomes)),
        pass_stdev=statistics.pstdev(outcomes) if len(outcomes) > 1 else 0.0,
        axes=_axis_statistics(attempts),
        measurements=_measurements(attempts),
        deviations=sum(1 for score in attempts if score.deviated_from_golden),
        different_valid_routes=sum(1 for score in attempts if score.different_valid_route),
        failed_axes=tuple(sorted(failed, key=SCORING_AXES.index)),
    )


def _axis_statistics(attempts: Sequence[ScenarioScore]) -> tuple[AxisStatistic, ...]:
    """Return one statistic per axis over the attempts that asserted it."""
    found: list[AxisStatistic] = []
    for name in SCORING_AXES:
        outcomes = [
            1.0 if axis.passed else 0.0
            for axis in (score.axis(name) for score in attempts)
            if axis is not None and axis.applicable
        ]
        found.append(
            AxisStatistic(
                axis=name,
                attempts=len(outcomes),
                passes=int(sum(outcomes)),
                stdev=statistics.pstdev(outcomes) if len(outcomes) > 1 else 0.0,
            )
        )
    return tuple(found)


def _corpus_axes(scores: Sequence[ScenarioScore]) -> tuple[AxisStatistic, ...]:
    """Return one statistic per axis over every attempt in the whole run."""
    return _axis_statistics(scores)


def _measurements(attempts: Sequence[ScenarioScore]) -> tuple[Measurement, ...]:
    """Return the tracked numbers, averaged with their spread."""
    found: list[Measurement] = []
    for axis, name in TRACKED_MEASUREMENTS:
        values = [
            score.measurement(axis, name)
            for score in attempts
            if score.axis(axis) is not None and name in (score.axis(axis) or _NO_AXIS).measurements
        ]
        found.append(Measurement.of(f"{axis}.{name}", values))
    return tuple(found)


class _NoAxis:
    """Stand-in with an empty measurement map, so the guard above reads plainly."""

    measurements: Mapping[str, float] = {}


_NO_AXIS = _NoAxis()


def _group(
    scenarios: Sequence[ScenarioStatistic],
    *,
    key: Any,
    difficulty: Any,
    description: Any,
    order: Any,
) -> tuple[GroupStatistic, ...]:
    """Return ``scenarios`` grouped by ``key``, aggregated and ordered."""
    buckets: dict[str, list[ScenarioStatistic]] = {}
    for found in scenarios:
        buckets.setdefault(key(found), []).append(found)

    groups = [
        GroupStatistic(
            name=name,
            attempts=sum(found.attempts for found in members),
            passes=sum(found.passes for found in members),
            difficulty=difficulty(members[0]),
            description=description(members[0]),
            scenarios=tuple(found.key for found in members),
        )
        for name, members in buckets.items()
    ]
    return tuple(sorted(groups, key=order))


def corpus_version(keys: Iterable[str]) -> str:
    """Return a short digest of which scenarios a run covered.

    Recorded on a baseline so that a corpus change is visible as a corpus change
    rather than as an agent regression. A scenario added, retired, or renamed
    moves this string, and the gate refuses to compare across two of them.
    """
    import hashlib

    digest = hashlib.sha256("\n".join(sorted(keys)).encode("utf-8")).hexdigest()
    return digest[:16]


__all__ = [
    "TRACKED_MEASUREMENTS",
    "AxisStatistic",
    "GroupStatistic",
    "Measurement",
    "ScenarioStatistic",
    "SuiteScore",
    "corpus_version",
    "summarise",
]
