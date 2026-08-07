"""One attempt, five axes, and the rule that combines them without hiding them.

The composite is the smallest part of this package and the one with the most
opportunity to destroy the value of the rest. Two decisions keep it honest.

**Every axis is scored, always.** Not "until one fails". A scenario that failed
on accuracy still has a trajectory worth knowing about — a wrong answer reached
in two calls and a wrong answer reached in nineteen are different problems — and
short-circuiting would make the cheap half of the diagnosis unavailable exactly
when somebody needs it.

**Only asserted axes gate.** An answer key states what its author was willing to
defend. Folding the unasserted ones into the pass count as free wins would make
a suite's adversarial number mostly scenarios that planted no confounder, which
flatters the agent and measures the corpus.

``Observation`` is the seam. Scoring takes what an attempt *did* rather than the
attempt itself, so an axis can be tested in five lines, a stored corpus run can
be re-scored without being re-executed, and an ablation arm that produced its
result some other way is scored by the same code as one that ran the pipeline.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from config.constants.evaluation import (
    AXIS_ACCURACY,
    AXIS_ADVERSARIAL,
    AXIS_COST,
    AXIS_EVIDENCE,
    AXIS_TRAJECTORY,
    CORRECTNESS_AXES,
    SCORING_AXES,
)
from core.domain.diagnosis.result import Claim
from tests.harness.loader import Scenario
from tests.harness.scoring.axes.accuracy import score_accuracy
from tests.harness.scoring.axes.adversarial import score_adversarial
from tests.harness.scoring.axes.cost import CostBudget, score_cost
from tests.harness.scoring.axes.evidence import score_evidence
from tests.harness.scoring.axes.result import AxisScore
from tests.harness.scoring.axes.trajectory import score_trajectory
from tests.harness.scoring.matching import Step, flatten, steps_from_iterations

if TYPE_CHECKING:  # pragma: no cover - import cycle at type-check time only
    from tests.harness.runner import ScenarioRun


@dataclass(frozen=True, slots=True)
class Observation:
    """What one attempt did, as the five scorers read it.

    A value rather than a view onto a ``ScenarioRun``, because the scorers must
    work on a stored record as readily as on a live run — re-scoring a corpus
    without re-executing it is the property that makes baselines affordable.
    """

    root_cause_category: str = "unknown"
    answer_text: str = ""
    evidence_sources: tuple[str, ...] = ()
    validated_claims: tuple[Claim, ...] = ()
    held_evidence_ids: frozenset[str] = frozenset()
    trajectory: tuple[Step, ...] = ()
    iterations: int = 0
    tokens: int = 0
    duration_seconds: float = 0.0
    provider_id: str = ""
    model_id: str = ""

    def as_overrides(self) -> dict[str, Any]:
        """Return this observation as keyword arguments, for building a variant.

        Present so a test can state the one thing it changed rather than
        restating nine fields it does not care about, which is what makes the
        axis-independence assertions readable.
        """
        return {
            "root_cause_category": self.root_cause_category,
            "answer_text": self.answer_text,
            "evidence_sources": self.evidence_sources,
            "validated_claims": self.validated_claims,
            "held_evidence_ids": self.held_evidence_ids,
            "trajectory": self.trajectory,
            "iterations": self.iterations,
            "tokens": self.tokens,
            "duration_seconds": self.duration_seconds,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
        }


def observation_of(run: ScenarioRun) -> Observation:
    """Return what a pipeline run did, in the shape the scorers take.

    The trajectory is grouped by the iteration each call was made in, which is
    what turns FR-009 from an intention into a fact: whatever the loop dispatched
    together is one position, whichever coroutine happened to finish first.
    """
    entries = run.run.state.evidence.entries
    diagnosis = run.diagnosis
    return Observation(
        root_cause_category=run.root_cause_category,
        answer_text=run.answer_text,
        evidence_sources=run.evidence_sources,
        validated_claims=diagnosis.validated_claims if diagnosis is not None else (),
        held_evidence_ids=run.run.state.evidence.ids,
        trajectory=steps_from_iterations(
            (entry.provenance.iteration, entry.capability) for entry in entries
        ),
        iterations=run.iterations,
        tokens=run.tokens,
        duration_seconds=run.duration_seconds,
        provider_id=run.provider_id,
        model_id=run.model_id,
    )


@dataclass(frozen=True, slots=True)
class ScenarioScore:
    """One attempt at one scenario, on every axis, with nothing collapsed."""

    key: str
    suite: str
    scenario_id: str
    difficulty: int
    failure_mode: str
    axes: tuple[AxisScore, ...] = ()
    attempt: int = 1
    adversarial_signals: tuple[str, ...] = ()
    provider_id: str = ""
    model_id: str = ""
    trajectory: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        """Return whether every axis this answer key asserted held (FR-007)."""
        return not any(axis.failed for axis in self.axes)

    @property
    def failed_axes(self) -> tuple[str, ...]:
        """Return the asserted axes that did not hold, in reading order."""
        return tuple(axis.name for axis in self.axes if axis.failed)

    @property
    def asserted_axes(self) -> tuple[str, ...]:
        """Return the axes this answer key had an opinion about."""
        return tuple(axis.name for axis in self.axes if axis.applicable)

    def axis(self, name: str) -> AxisScore | None:
        """Return the result for the axis called ``name``, or ``None``."""
        return next((found for found in self.axes if found.name == name), None)

    @property
    def deviated_from_golden(self) -> bool:
        """Return whether the route differed from the one the answer key names."""
        trajectory = self.axis(AXIS_TRAJECTORY)
        return trajectory is not None and bool(trajectory.measurements.get("deviated", 0.0))

    @property
    def different_valid_route(self) -> bool:
        """Return whether this attempt was right and got there another way (FR-011).

        The distinction SC-009 asks for. A run that deviated *and* was wrong is
        simply wrong; reporting it as an interesting route would put every
        failure in the deviation list and make the list worthless.
        """
        if not self.deviated_from_golden:
            return False
        return all(
            axis.passed for axis in self.axes if axis.name in CORRECTNESS_AXES and axis.applicable
        )

    def measurement(self, axis: str, name: str, default: float = 0.0) -> float:
        """Return one number from one axis, or ``default`` when it was not recorded."""
        found = self.axis(axis)
        return float(found.measurements.get(name, default)) if found is not None else default

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this score."""
        return {
            "key": self.key,
            "suite": self.suite,
            "scenario": self.scenario_id,
            "difficulty": self.difficulty,
            "failure_mode": self.failure_mode,
            "attempt": self.attempt,
            "passed": self.passed,
            "failed_axes": list(self.failed_axes),
            "different_valid_route": self.different_valid_route,
            "adversarial_signals": list(self.adversarial_signals),
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "trajectory": list(self.trajectory),
            "axes": [axis.to_record() for axis in self.axes],
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> ScenarioScore:
        """Return the score a stored record describes."""
        return cls(
            key=str(record["key"]),
            suite=str(record.get("suite", "")),
            scenario_id=str(record.get("scenario", "")),
            difficulty=int(record.get("difficulty", 0)),
            failure_mode=str(record.get("failure_mode", "")),
            attempt=int(record.get("attempt", 1)),
            adversarial_signals=tuple(
                str(item) for item in record.get("adversarial_signals") or ()
            ),
            provider_id=str(record.get("provider_id", "")),
            model_id=str(record.get("model_id", "")),
            trajectory=tuple(str(item) for item in record.get("trajectory") or ()),
            axes=tuple(AxisScore.from_record(item) for item in record.get("axes") or ()),
        )


def score_observation(
    scenario: Scenario,
    observation: Observation,
    *,
    attempt: int = 1,
    budget: CostBudget | None = None,
) -> ScenarioScore:
    """Return ``observation`` scored against ``scenario``'s answer key, on all five axes.

    Every axis runs. None of them short-circuits on an earlier failure, because
    the reason to have five is that the four a failure did not cause are what
    tell somebody what to do about it.
    """
    answer = scenario.answer
    axes = (
        score_accuracy(
            answer, category=observation.root_cause_category, said=observation.answer_text
        ),
        score_evidence(
            answer,
            sources=observation.evidence_sources,
            claims=observation.validated_claims,
            held=observation.held_evidence_ids,
        ),
        score_adversarial(answer, said=observation.answer_text),
        score_trajectory(
            answer, trajectory=observation.trajectory, iterations=observation.iterations
        ),
        score_cost(
            budget if budget is not None else CostBudget.for_difficulty(scenario.difficulty),
            tokens=observation.tokens,
            seconds=observation.duration_seconds,
        ),
    )
    return ScenarioScore(
        key=scenario.key,
        suite=scenario.suite,
        scenario_id=scenario.scenario_id,
        difficulty=scenario.difficulty,
        failure_mode=scenario.failure_mode,
        attempt=attempt,
        adversarial_signals=scenario.adversarial_signals,
        provider_id=observation.provider_id,
        model_id=observation.model_id,
        trajectory=flatten(observation.trajectory),
        axes=_in_reading_order(axes),
    )


def score_run(run: ScenarioRun, *, budget: CostBudget | None = None) -> ScenarioScore:
    """Return one pipeline run scored against its scenario's answer key."""
    return score_observation(run.scenario, observation_of(run), attempt=run.attempt, budget=budget)


def _in_reading_order(axes: Sequence[AxisScore]) -> tuple[AxisScore, ...]:
    """Return ``axes`` in the declared order, so every record reads the same way."""
    found: dict[str, AxisScore] = {axis.name: axis for axis in axes}
    return tuple(found[name] for name in SCORING_AXES if name in found)


#: Re-exported so a caller scoring one axis does not have to know which module it
#: lives in. The axis modules stay separate; the import does not have to be.
AXES: tuple[str, ...] = (
    AXIS_ACCURACY,
    AXIS_EVIDENCE,
    AXIS_ADVERSARIAL,
    AXIS_TRAJECTORY,
    AXIS_COST,
)


__all__ = [
    "AXES",
    "AxisScore",
    "Observation",
    "ScenarioScore",
    "observation_of",
    "score_observation",
    "score_run",
]
