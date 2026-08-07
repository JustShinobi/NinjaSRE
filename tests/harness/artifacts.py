"""The per-attempt verdict record: enough to explain a failure without re-running it.

SC-004 is the requirement and it is a high bar: somebody who was not there has
to be able to read one line and say what went wrong. A record that said
``{"scenario": "004", "passed": false}`` meets none of it. It sends the reader
back to the corpus with a stopwatch, and in practice it means nobody diagnoses
anything and the suite becomes a number people watch rather than a tool people
use.

So a record carries three things: what the answer key asked for, what the run
actually did, and per axis, the difference. The axes are checked here because a
verdict has to be *decidable* for the suite to report a solve rate at all — but
nothing here weights them, ranks them, or turns them into a score. That belongs
to the scoring feature, and keeping the split is what lets a stored corpus run
be re-scored without being re-executed.

Writing is off unless an environment variable names a file (FR-020). The
alternative — a flag threaded through the runner, the suite, and every caller —
would be four places to forget, and the reason to have records at all is that
the interesting run is usually the one nobody expected to need.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config.constants.evaluation import NINJASRE_SCENARIO_ARTIFACTS_ENV
from tests.harness.determinism import DETERMINISTIC, DeterministicProfile
from tests.harness.loader import AnswerKey, GoldenTrajectory
from tests.harness.runner import ScenarioRun


@dataclass(frozen=True, slots=True)
class AxisResult:
    """One answer-key axis, checked, with both sides of the comparison kept.

    ``expected`` and ``observed`` are both recorded even when the axis passed.
    A reader comparing two runs of the same scenario needs the second one's
    observed value to see what changed, and a record that only kept the losing
    side would make every comparison a re-run.
    """

    name: str
    passed: bool
    expected: tuple[str, ...] = ()
    observed: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    unexpected: tuple[str, ...] = ()
    detail: str = ""

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this axis."""
        return {
            "name": self.name,
            "passed": self.passed,
            "expected": list(self.expected),
            "observed": list(self.observed),
            "missing": list(self.missing),
            "unexpected": list(self.unexpected),
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class Verdict:
    """One attempt, scored against its answer key, with the working shown."""

    run: ScenarioRun
    axes: tuple[AxisResult, ...] = ()
    profile: DeterministicProfile = DETERMINISTIC

    @property
    def passed(self) -> bool:
        """Return whether every axis the answer key asserted held."""
        return all(axis.passed for axis in self.axes)

    @property
    def failed_axes(self) -> tuple[str, ...]:
        """Return the names of the axes that did not hold, in report order."""
        return tuple(axis.name for axis in self.axes if not axis.passed)

    def axis(self, name: str) -> AxisResult | None:
        """Return the result for the axis called ``name``, or ``None``."""
        return next((found for found in self.axes if found.name == name), None)

    def to_record(self) -> dict[str, Any]:
        """Return the JSONL line this attempt is recorded as (FR-018)."""
        scenario = self.run.scenario
        return {
            "suite": scenario.suite,
            "scenario": scenario.scenario_id,
            "title": scenario.title,
            "attempt": self.run.attempt,
            "passed": self.passed,
            "failed_axes": list(self.failed_axes),
            "difficulty": scenario.difficulty,
            "difficulty_description": scenario.difficulty_description,
            "failure_mode": scenario.failure_mode,
            "adversarial_signals": list(scenario.adversarial_signals),
            "expected_root_cause_category": scenario.answer.root_cause_category,
            "agent_root_cause_category": self.run.root_cause_category,
            "agent_root_cause": (
                self.run.diagnosis.root_cause if self.run.diagnosis is not None else ""
            ),
            "agent_summary": (self.run.diagnosis.summary if self.run.diagnosis is not None else ""),
            "confidence": (
                self.run.diagnosis.confidence if self.run.diagnosis is not None else 0.0
            ),
            "trajectory": list(self.run.trajectory),
            "evidence_sources": list(self.run.evidence_sources),
            "vendor_calls": [
                {
                    "integration": call.integration,
                    "method": call.method,
                    "path": call.path,
                    "status": call.status,
                    "matched": call.matched,
                    "fixture": call.fixture,
                }
                for call in self.run.boundary.calls
            ],
            "iterations": self.run.iterations,
            "tokens": self.run.tokens,
            "duration_seconds": round(self.run.duration_seconds, 3),
            "provider_id": self.run.provider_id,
            "model_id": self.run.model_id,
            "pipeline_succeeded": self.run.run.succeeded,
            "failed_stage": (
                self.run.run.failed_stage.value if self.run.run.failed_stage is not None else ""
            ),
            "pipeline_failure": self.run.run.failure,
            "determinism": self.profile.to_record(),
            "axes": [axis.to_record() for axis in self.axes],
        }


def _contains_all(haystack: str, needles: Sequence[str]) -> tuple[list[str], list[str]]:
    """Return the needles present in ``haystack`` and the ones absent, case-folded."""
    folded = haystack.lower()
    present = [needle for needle in needles if needle.lower() in folded]
    absent = [needle for needle in needles if needle.lower() not in folded]
    return present, absent


def _trajectory_axis(golden: GoldenTrajectory, trajectory: Sequence[str]) -> AxisResult:
    """Return whether ``trajectory`` satisfies ``golden``, and how it differed."""
    actual = list(trajectory)
    expected = list(golden.ordered_actions)

    if golden.matching == "set":
        missing = [action for action in expected if action not in actual]
        satisfied = not missing
        detail = "actions present in any order"
    elif golden.matching == "exact":
        missing = [action for action in expected if action not in actual]
        satisfied = actual[: len(expected)] == expected
        detail = "the exact sequence, in order and adjacent"
    else:
        kept = _longest_common_subsequence(expected, actual)
        missing = [action for action in expected if action not in kept]
        satisfied = len(expected) - len(kept) <= golden.max_edit_distance
        detail = f"longest common subsequence kept {len(kept)} of {len(expected)}"

    extra = [action for action in actual if action not in expected]
    if satisfied and len(extra) > golden.max_extra_actions:
        satisfied = False
        detail = f"{len(extra)} actions beyond the golden path, at most {golden.max_extra_actions}"

    redundant = len(actual) - len(set(actual))
    if satisfied and redundant > golden.max_redundancy:
        satisfied = False
        detail = f"{redundant} repeated calls, at most {golden.max_redundancy}"

    return AxisResult(
        name="trajectory",
        passed=satisfied,
        expected=tuple(expected),
        observed=tuple(actual),
        missing=tuple(missing),
        unexpected=tuple(extra),
        detail=detail,
    )


def _longest_common_subsequence(expected: Sequence[str], actual: Sequence[str]) -> list[str]:
    """Return the longest ordered subsequence common to both."""
    table = [[0] * (len(actual) + 1) for _ in range(len(expected) + 1)]
    for i in range(len(expected) - 1, -1, -1):
        for j in range(len(actual) - 1, -1, -1):
            table[i][j] = (
                table[i + 1][j + 1] + 1
                if expected[i] == actual[j]
                else max(table[i + 1][j], table[i][j + 1])
            )
    kept: list[str] = []
    i = j = 0
    while i < len(expected) and j < len(actual):
        if expected[i] == actual[j]:
            kept.append(expected[i])
            i += 1
            j += 1
        elif table[i + 1][j] >= table[i][j + 1]:
            i += 1
        else:
            j += 1
    return kept


def verdict_for(run: ScenarioRun, *, profile: DeterministicProfile = DETERMINISTIC) -> Verdict:
    """Return ``run`` checked against its scenario's answer key.

    Only the axes the answer key actually declares are checked. An axis nobody
    asserted is not a silent pass hiding in the record; it is simply absent,
    which is what makes ``failed_axes`` readable and what keeps a key honest
    about what its author was willing to defend.
    """
    answer: AnswerKey = run.scenario.answer
    said = run.answer_text
    axes: list[AxisResult] = []

    observed_category = run.root_cause_category
    axes.append(
        AxisResult(
            name="root_cause_category",
            passed=observed_category in answer.accepted_categories,
            expected=tuple(sorted(answer.accepted_categories)),
            observed=(observed_category,),
            detail="equality against the shipped taxonomy",
        )
    )

    present, absent = _contains_all(said, answer.required_keywords)
    axes.append(
        AxisResult(
            name="required_keywords",
            passed=not absent,
            expected=answer.required_keywords,
            observed=tuple(present),
            missing=tuple(absent),
            detail="case-insensitive substring over everything the agent said",
        )
    )

    if answer.forbidden_keywords:
        found, _ = _contains_all(said, answer.forbidden_keywords)
        axes.append(
            AxisResult(
                name="forbidden_keywords",
                passed=not found,
                expected=answer.forbidden_keywords,
                observed=tuple(found),
                unexpected=tuple(found),
                detail="none of these may appear",
            )
        )

    if answer.ruling_out_keywords:
        ruled, unruled = _contains_all(said, answer.ruling_out_keywords)
        axes.append(
            AxisResult(
                name="ruling_out_keywords",
                passed=not unruled,
                expected=answer.ruling_out_keywords,
                observed=tuple(ruled),
                missing=tuple(unruled),
                detail="the planted confounders must be dismissed explicitly (FR-022)",
            )
        )

    if answer.required_evidence_sources:
        sources = run.evidence_sources
        absent_sources = [name for name in answer.required_evidence_sources if name not in sources]
        axes.append(
            AxisResult(
                name="required_evidence_sources",
                passed=not absent_sources,
                expected=answer.required_evidence_sources,
                observed=sources,
                missing=tuple(absent_sources),
                detail="the conclusion has to rest on the evidence that was planted",
            )
        )

    if answer.required_queries:
        asked = "\n".join(call.url for call in run.boundary.calls)
        found_queries, missing_queries = _contains_all(asked, answer.required_queries)
        axes.append(
            AxisResult(
                name="required_queries",
                passed=not missing_queries,
                expected=answer.required_queries,
                observed=tuple(found_queries),
                missing=tuple(missing_queries),
                detail="substring over every vendor URL the run reached",
            )
        )

    if answer.forbidden_categories:
        offending = [name for name in answer.forbidden_categories if name == observed_category]
        axes.append(
            AxisResult(
                name="root_cause_category",
                passed=not offending,
                expected=answer.forbidden_categories,
                observed=(observed_category,),
                unexpected=tuple(offending),
                detail="categories this scenario must not be attributed to",
            )
            if offending
            else AxisResult(
                name="forbidden_categories",
                passed=True,
                expected=answer.forbidden_categories,
                observed=(observed_category,),
                detail="categories this scenario must not be attributed to",
            )
        )

    if answer.golden_trajectory is not None:
        axes.append(_trajectory_axis(answer.golden_trajectory, run.trajectory))
    elif answer.optimal_trajectory:
        missing_actions = [
            action for action in answer.optimal_trajectory if action not in run.trajectory
        ]
        axes.append(
            AxisResult(
                name="trajectory",
                passed=not missing_actions,
                expected=answer.optimal_trajectory,
                observed=run.trajectory,
                missing=tuple(missing_actions),
                detail="every optimal action was taken, in any order",
            )
        )

    ceiling = answer.max_investigation_loops
    if ceiling is not None:
        axes.append(
            AxisResult(
                name="investigation_loops",
                passed=run.iterations <= ceiling,
                expected=(str(ceiling),),
                observed=(str(run.iterations),),
                detail="Article II: the answer key's own ceiling for this incident",
            )
        )

    return Verdict(run=run, axes=_deduplicate(axes), profile=profile)


def _deduplicate(axes: Sequence[AxisResult]) -> tuple[AxisResult, ...]:
    """Return ``axes`` with a failing result winning over a passing one of its name.

    ``forbidden_categories`` reports under ``root_cause_category`` when it is
    what failed, because that is the axis a reader is looking for — and two
    results for one name would make ``failed_axes`` ambiguous.
    """
    kept: dict[str, AxisResult] = {}
    for axis in axes:
        existing = kept.get(axis.name)
        if existing is None or (existing.passed and not axis.passed):
            kept[axis.name] = axis
    return tuple(kept.values())


@dataclass(slots=True)
class ArtifactWriter:
    """Appends one JSON line per attempt, or does nothing at all.

    ``path`` of ``None`` is the default and is not an error state: it is what
    "records are off" means, and a writer that had to be conditionally
    constructed would put that condition at every call site.
    """

    path: Path | None = None
    written: int = 0
    _opened: bool = field(default=False, repr=False)

    def write(self, verdict: Verdict) -> None:
        """Append ``verdict`` to the record file, if there is one."""
        if self.path is None:
            return
        if not self._opened:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._opened = True
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(verdict.to_record(), sort_keys=True) + "\n")
        self.written += 1


def writer_from_environment() -> ArtifactWriter:
    """Return the writer the environment asks for, or one that writes nothing."""
    configured = os.environ.get(NINJASRE_SCENARIO_ARTIFACTS_ENV, "").strip()
    return ArtifactWriter(path=Path(configured)) if configured else ArtifactWriter()


def read_records(path: Path) -> tuple[dict[str, Any], ...]:
    """Return every verdict record stored at ``path``."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return tuple(json.loads(line) for line in lines if line.strip())


__all__ = [
    "ArtifactWriter",
    "AxisResult",
    "Verdict",
    "read_records",
    "verdict_for",
    "writer_from_environment",
]
