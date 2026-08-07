"""Running many scenarios: filtering, repeat attempts, and what came back.

One executor, two front doors. The pytest path and the command-line path both
end up here, because a suite that behaved differently under ``pytest`` from
under ``make test-synthetic`` would produce two numbers and no way to say which
one is the score.

Repeat attempts exist for variance (FR-014), and variance is the thing a single
run cannot tell you. A scenario that passes four times in five is a different
signal from one that passes every time, and both look identical at one attempt.
The default is one attempt because measuring variance is something you opt into
— paying five times for every ordinary run would make the cheap path the
expensive one.

Nothing here scores. The suite collects attempts; the answer key is applied in
``artifacts``, and the weighting of the axes belongs to the scoring feature.
Keeping the split means the same corpus run can be re-scored without being
re-executed, which is the whole reason verdict records are worth writing.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.constants.evaluation import (
    DEFAULT_SCENARIO_ATTEMPTS,
    MAX_SCENARIO_ATTEMPTS,
    SCENARIO_DIFFICULTY_DESCRIPTIONS,
)
from core.llm.types import LLMClient
from tests.harness.loader import Scenario, discover_scenarios, filter_scenarios
from tests.harness.runner import ScenarioRun, run_scenario

#: How a caller supplies the model for one attempt. A factory rather than a
#: client, because a scripted or replayed provider is scenario-specific and a
#: shared one would carry the previous scenario's queue into the next.
ProviderFactory = Callable[[Scenario, int], LLMClient]

#: Called as each attempt finishes, so a long run can report progress without
#: the suite knowing what a progress report looks like.
AttemptObserver = Callable[[ScenarioRun], None]


@dataclass(frozen=True, slots=True)
class SuiteResult:
    """Every attempt a suite run made, in the order it made them."""

    runs: tuple[ScenarioRun, ...] = ()
    duration_seconds: float = 0.0

    @property
    def scenarios(self) -> tuple[Scenario, ...]:
        """Return each scenario that was run, once, in order."""
        seen: dict[str, Scenario] = {}
        for run in self.runs:
            seen.setdefault(run.scenario.key, run.scenario)
        return tuple(seen.values())

    @property
    def attempts(self) -> int:
        """Return how many attempts were made in total."""
        return len(self.runs)

    def for_scenario(self, key: str) -> tuple[ScenarioRun, ...]:
        """Return every attempt at the scenario identified by ``key``."""
        return tuple(run for run in self.runs if run.scenario.key == key)


def load_suite(
    root: Path,
    *,
    suite: str = "",
    scenario_id: str = "",
    difficulty: int | None = None,
    integration: str = "",
    offline_only: bool = False,
) -> tuple[Scenario, ...]:
    """Return the scenarios under ``root`` that match every filter given (FR-013)."""
    return filter_scenarios(
        discover_scenarios(root),
        suite=suite,
        scenario_id=scenario_id,
        difficulty=difficulty,
        integration=integration,
        offline_only=offline_only,
    )


async def run_suite(
    scenarios: Sequence[Scenario],
    *,
    provider: ProviderFactory,
    attempts: int = DEFAULT_SCENARIO_ATTEMPTS,
    observer: AttemptObserver | None = None,
) -> SuiteResult:
    """Return every attempt at every scenario in ``scenarios``.

    Attempts run in sequence rather than concurrently. The corpus is small, the
    offline path is fast, and concurrency here would make wall-clock time — one
    of the things SC-008 asserts about — depend on how many cores the machine
    that ran it had.

    Raises:
        ValueError: ``attempts`` is outside the bound Article II sets on it.
    """
    if not 1 <= attempts <= MAX_SCENARIO_ATTEMPTS:
        raise ValueError(f"attempts must be between 1 and {MAX_SCENARIO_ATTEMPTS}, got {attempts}")

    started = time.perf_counter()
    runs: list[ScenarioRun] = []
    for scenario in scenarios:
        for attempt in range(1, attempts + 1):
            run = await run_scenario(scenario, llm=provider(scenario, attempt), attempt=attempt)
            runs.append(run)
            if observer is not None:
                observer(run)
    return SuiteResult(runs=tuple(runs), duration_seconds=time.perf_counter() - started)


# -- reporting ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ScenarioReport:
    """One scenario's outcome across every attempt made at it.

    ``solve_rate`` rather than a bare pass, because the two scenarios worth
    retiring are invisible at one attempt: the one nothing ever solves, which is
    a target once and then noise, and the one everything solves, which stopped
    discriminating between models the day it was written.
    """

    key: str
    suite: str
    scenario_id: str
    difficulty: int
    failure_mode: str
    adversarial_signals: tuple[str, ...]
    attempts: int
    passes: int
    failed_axes: tuple[str, ...] = ()

    @property
    def solve_rate(self) -> float:
        """Return the share of attempts that passed."""
        return self.passes / self.attempts if self.attempts else 0.0

    @property
    def permanently_unsolved(self) -> bool:
        """Return whether no attempt has ever passed this scenario."""
        return self.attempts > 0 and self.passes == 0

    @property
    def trivially_solved(self) -> bool:
        """Return whether every attempt passed, which is only informative at scale."""
        return self.attempts > 0 and self.passes == self.attempts


@dataclass(frozen=True, slots=True)
class DifficultyReport:
    """Every scenario at one level of the curriculum, together."""

    difficulty: int
    description: str
    scenarios: tuple[ScenarioReport, ...] = ()

    @property
    def attempts(self) -> int:
        """Return how many attempts were made at this level."""
        return sum(found.attempts for found in self.scenarios)

    @property
    def passes(self) -> int:
        """Return how many of them passed."""
        return sum(found.passes for found in self.scenarios)

    @property
    def solve_rate(self) -> float:
        """Return this level's solve rate."""
        return self.passes / self.attempts if self.attempts else 0.0


@dataclass(frozen=True, slots=True)
class SuiteReport:
    """What a suite run says, at the granularities anybody asks for it at."""

    scenarios: tuple[ScenarioReport, ...] = ()
    duration_seconds: float = 0.0

    @property
    def attempts(self) -> int:
        """Return how many attempts the run made in total."""
        return sum(found.attempts for found in self.scenarios)

    @property
    def passes(self) -> int:
        """Return how many attempts passed."""
        return sum(found.passes for found in self.scenarios)

    @property
    def solve_rate(self) -> float:
        """Return the whole run's solve rate."""
        return self.passes / self.attempts if self.attempts else 0.0

    def by_difficulty(self) -> tuple[DifficultyReport, ...]:
        """Return one report per level present, easiest first (SC-007).

        Reporting by level is what distinguishes an improvement that helped
        everywhere from one that helped on the easy cases — and only the first
        is a capability change.
        """
        levels: dict[int, list[ScenarioReport]] = {}
        for found in self.scenarios:
            levels.setdefault(found.difficulty, []).append(found)
        return tuple(
            DifficultyReport(
                difficulty=level,
                description=SCENARIO_DIFFICULTY_DESCRIPTIONS.get(level, ""),
                scenarios=tuple(found),
            )
            for level, found in sorted(levels.items())
        )

    @property
    def permanently_unsolved(self) -> tuple[ScenarioReport, ...]:
        """Return the scenarios nothing solved, which are candidates for retirement."""
        return tuple(found for found in self.scenarios if found.permanently_unsolved)

    @property
    def trivially_solved(self) -> tuple[ScenarioReport, ...]:
        """Return the scenarios everything solved, which have stopped discriminating."""
        return tuple(found for found in self.scenarios if found.trivially_solved)

    def to_record(self) -> dict[str, Any]:
        """Return the report as a JSON-serialisable document."""
        return {
            "attempts": self.attempts,
            "passes": self.passes,
            "solve_rate": round(self.solve_rate, 4),
            "duration_seconds": round(self.duration_seconds, 3),
            "by_difficulty": [
                {
                    "difficulty": level.difficulty,
                    "description": level.description,
                    "attempts": level.attempts,
                    "passes": level.passes,
                    "solve_rate": round(level.solve_rate, 4),
                }
                for level in self.by_difficulty()
            ],
            "scenarios": [
                {
                    "scenario": found.key,
                    "difficulty": found.difficulty,
                    "failure_mode": found.failure_mode,
                    "attempts": found.attempts,
                    "passes": found.passes,
                    "solve_rate": round(found.solve_rate, 4),
                    "failed_axes": list(found.failed_axes),
                }
                for found in self.scenarios
            ],
        }


def report_for(result: SuiteResult, *, writer: Any = None) -> SuiteReport:
    """Return ``result`` scored against the answer keys, aggregated per scenario.

    ``writer`` is the verdict-record writer, which is off by default — passing
    one is how a caller turns records on for a run without the suite growing a
    flag it threads through every layer.
    """
    from tests.harness.artifacts import verdict_for

    per_scenario: dict[str, list[Any]] = {}
    for run in result.runs:
        verdict = verdict_for(run)
        if writer is not None:
            writer.write(verdict)
        per_scenario.setdefault(run.scenario.key, []).append(verdict)

    reports: list[ScenarioReport] = []
    for key, verdicts in per_scenario.items():
        scenario = verdicts[0].run.scenario
        failed: list[str] = []
        for verdict in verdicts:
            failed.extend(axis for axis in verdict.failed_axes if axis not in failed)
        reports.append(
            ScenarioReport(
                key=key,
                suite=scenario.suite,
                scenario_id=scenario.scenario_id,
                difficulty=scenario.difficulty,
                failure_mode=scenario.failure_mode,
                adversarial_signals=scenario.adversarial_signals,
                attempts=len(verdicts),
                passes=sum(1 for verdict in verdicts if verdict.passed),
                failed_axes=tuple(failed),
            )
        )
    return SuiteReport(
        scenarios=tuple(sorted(reports, key=lambda found: (found.difficulty, found.key))),
        duration_seconds=result.duration_seconds,
    )


__all__ = [
    "AttemptObserver",
    "DifficultyReport",
    "ProviderFactory",
    "ScenarioReport",
    "SuiteReport",
    "SuiteResult",
    "load_suite",
    "report_for",
    "run_suite",
]
