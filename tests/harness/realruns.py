"""Scoring a run that happened against real infrastructure, on the same five axes.

Feature 028's axes are not re-implemented here and must not be. A chaos run
scored by different arithmetic from a synthetic one would produce two numbers
that look comparable and are not, and the whole point of running the expensive
suite is to find out whether the cheap suite's improvements transfer.

What is added is the one thing a real run has and a fixture does not: it might
not have happened. An injected fault that never took effect, a demo whose flag
did not propagate, a cloud resource that never came up — each produces a run
that scores badly for a reason that has nothing to do with the agent. So every
real run carries a **validity**, and an invalid one is reported rather than
scored. Folding those into the pass rate is the specific way an expensive suite
becomes a source of noise nobody trusts and then nobody runs.

Three validities, not two, because "the probe could not be read" is neither a
working experiment nor a broken one, and collapsing it into either direction
loses a real experiment or invents a real measurement.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from config.constants.evaluation import SCORING_AXES
from tests.harness.loader import AnswerKey, Scenario
from tests.harness.scoring.axes.cost import CostBudget
from tests.harness.scoring.composite import Observation, ScenarioScore, score_observation
from tests.harness.scoring.report import SuiteScore, corpus_version, summarise


class RunValidity(StrEnum):
    """Whether a real run measured the agent at all."""

    VALID = "valid"
    INVALID = "invalid"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class RealRunExpectation:
    """What a real run is scored against: an answer key, plus where it came from.

    Deliberately the same fields an ``answer.yml`` carries. A chaos experiment
    and an otel-demo fault declare their expectations in their own documents,
    and both arrive here in one shape so the scorer never learns which suite it
    is looking at.
    """

    key: str
    suite: str
    scenario_id: str
    failure_mode: str
    severity: str
    difficulty: int
    root_cause_category: str
    required_keywords: tuple[str, ...]
    equivalent_root_cause_categories: tuple[str, ...] = ()
    forbidden_categories: tuple[str, ...] = ()
    required_evidence_sources: tuple[str, ...] = ()
    optimal_trajectory: tuple[str, ...] = ()
    max_investigation_loops: int | None = None
    integrations: tuple[str, ...] = ()
    available_evidence: tuple[str, ...] = ()
    team_id: str = "payments"
    title: str = ""

    def as_scenario(
        self, *, directory: Path | None = None, alert: Mapping[str, Any] | None = None
    ) -> Scenario:
        """Return this expectation in the shape the five-axis scorer takes.

        A ``Scenario`` rather than a new type, because ``score_observation``
        already takes one and a parallel type would be a second definition of
        what an answer key is — which is exactly how two suites end up scoring
        the same answer differently.
        """
        return Scenario(
            directory=directory if directory is not None else Path(self.suite) / self.scenario_id,
            suite=self.suite,
            scenario_id=self.scenario_id,
            failure_mode=self.failure_mode,
            severity=self.severity,
            difficulty=self.difficulty,
            adversarial_signals=(),
            available_evidence=self.available_evidence or self.integrations,
            integrations=self.integrations,
            alert=dict(alert or {}),  # type: ignore[arg-type]
            answer=AnswerKey(
                root_cause_category=self.root_cause_category,
                required_keywords=self.required_keywords,
                model_response="",
                equivalent_root_cause_categories=self.equivalent_root_cause_categories,
                forbidden_categories=self.forbidden_categories,
                required_evidence_sources=self.required_evidence_sources,
                optimal_trajectory=self.optimal_trajectory,
                max_investigation_loops=self.max_investigation_loops,
            ),
            evidence=(),
            team_id=self.team_id,
            title=self.title,
        )


@dataclass(frozen=True, slots=True)
class RealRunScore:
    """One real run: whether it counted, and what it scored when it did."""

    key: str
    validity: RunValidity
    validity_detail: str = ""
    score: ScenarioScore | None = None
    attempt: int = 1
    run_id: str = ""

    @property
    def scored(self) -> bool:
        """Return whether this run is a measurement of the agent."""
        return self.validity is RunValidity.VALID and self.score is not None

    @property
    def passed(self) -> bool:
        """Return whether the agent got it right, which only valid runs can do."""
        return self.scored and self.score is not None and self.score.passed

    @property
    def agent_failure(self) -> bool:
        """Return whether the agent was wrong on a run that genuinely happened."""
        return self.scored and not self.passed

    @property
    def experiment_failure(self) -> bool:
        """Return whether the *experiment* failed rather than the agent."""
        return self.validity is RunValidity.INVALID

    @property
    def inconclusive(self) -> bool:
        """Return whether nothing can be said about this run either way."""
        return self.validity is RunValidity.UNKNOWN

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this run."""
        return {
            "key": self.key,
            "run_id": self.run_id,
            "attempt": self.attempt,
            "validity": self.validity.value,
            "validity_detail": self.validity_detail,
            "scored": self.scored,
            "passed": self.passed,
            "agent_failure": self.agent_failure,
            "experiment_failure": self.experiment_failure,
            "score": self.score.to_record() if self.score is not None else None,
        }


def score_real_run(
    expectation: RealRunExpectation,
    observation: Observation,
    *,
    validity: RunValidity,
    validity_detail: str = "",
    attempt: int = 1,
    run_id: str = "",
    budget: CostBudget | None = None,
    alert: Mapping[str, Any] | None = None,
) -> RealRunScore:
    """Return ``observation`` scored against ``expectation``, gated on ``validity``.

    An invalid run is still *observed* — the trajectory and the cost are real,
    and worth keeping — but it is not scored, because there is nothing to score
    it against: the evidence it read did not contain the fault the answer key
    names.
    """
    if validity is not RunValidity.VALID:
        return RealRunScore(
            key=expectation.key,
            validity=validity,
            validity_detail=validity_detail,
            attempt=attempt,
            run_id=run_id,
        )

    scenario = expectation.as_scenario(alert=alert)
    return RealRunScore(
        key=expectation.key,
        validity=validity,
        validity_detail=validity_detail,
        score=score_observation(scenario, observation, attempt=attempt, budget=budget),
        attempt=attempt,
        run_id=run_id,
    )


@dataclass(frozen=True, slots=True)
class RealRunReport:
    """Every real run in one suite execution, with the two failures kept apart.

    "Four experiments failed" is a sentence that means nothing until it says how
    many of the four were the agent's fault. This report's whole job is to make
    that distinction impossible to lose.
    """

    runs: tuple[RealRunScore, ...] = ()
    label: str = ""
    duration_seconds: float = 0.0
    attempted: tuple[str, ...] = field(default_factory=tuple)

    @property
    def scored(self) -> tuple[RealRunScore, ...]:
        """Return the runs that measured the agent."""
        return tuple(run for run in self.runs if run.scored)

    @property
    def agent_failures(self) -> tuple[RealRunScore, ...]:
        """Return the runs where the agent was wrong about a fault that was real."""
        return tuple(run for run in self.runs if run.agent_failure)

    @property
    def experiment_failures(self) -> tuple[RealRunScore, ...]:
        """Return the runs where the experiment did not produce its symptom."""
        return tuple(run for run in self.runs if run.experiment_failure)

    @property
    def inconclusive(self) -> tuple[RealRunScore, ...]:
        """Return the runs whose validity could not be established."""
        return tuple(run for run in self.runs if run.inconclusive)

    @property
    def pass_rate(self) -> float:
        """Return the share of *scored* runs the agent got right."""
        scored = self.scored
        if not scored:
            return 0.0
        return sum(1 for run in scored if run.passed) / len(scored)

    def suite_score(self) -> SuiteScore:
        """Return the scored runs aggregated the way any other suite run is.

        The corpus version is computed over everything that was *attempted*, not
        over what happened to be valid. A release where one experiment misfired
        would otherwise look like a corpus change, and the comparison would
        refuse for the wrong reason.
        """
        summary = summarise(
            [run.score for run in self.scored if run.score is not None],
            label=self.label,
            duration_seconds=self.duration_seconds,
        )
        keys = self.attempted or tuple(run.key for run in self.runs)
        return SuiteScore(
            scenarios=summary.scenarios,
            label=summary.label,
            corpus_version=corpus_version(keys),
            duration_seconds=summary.duration_seconds,
            attempts_per_scenario=summary.attempts_per_scenario,
            axes=summary.axes,
        )

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this report."""
        return {
            "label": self.label,
            "duration_seconds": round(self.duration_seconds, 3),
            "attempted": list(self.attempted or tuple(run.key for run in self.runs)),
            "scored": len(self.scored),
            "passed": sum(1 for run in self.scored if run.passed),
            "pass_rate": round(self.pass_rate, 4),
            "agent_failures": [run.key for run in self.agent_failures],
            "experiment_failures": [run.key for run in self.experiment_failures],
            "inconclusive": [run.key for run in self.inconclusive],
            "runs": [run.to_record() for run in self.runs],
        }

    def render(self) -> str:
        """Return the report a person reads, with the two failure kinds apart."""
        lines = [
            f"{self.label or 'real runs'}: {len(self.scored)} of {len(self.runs)} runs scored, "
            f"{self.pass_rate:.0%} passed"
        ]
        if self.agent_failures:
            lines.append("")
            lines.append("The agent was wrong about a fault that genuinely happened:")
            for run in self.agent_failures:
                axes = ", ".join(run.score.failed_axes) if run.score is not None else ""
                lines.append(f"  {run.key} — failed on {axes or 'no axis'}")
        if self.experiment_failures:
            lines.append("")
            lines.append("The experiment failed, not the agent — these are not scored:")
            for run in self.experiment_failures:
                lines.append(f"  {run.key} — {run.validity_detail}")
        if self.inconclusive:
            lines.append("")
            lines.append("Validity could not be established, so nothing is claimed:")
            for run in self.inconclusive:
                lines.append(f"  {run.key} — {run.validity_detail}")
        return "\n".join(lines)


def axis_rates(report: RealRunReport) -> dict[str, float]:
    """Return each axis's pass rate across the scored runs.

    The five axes rather than one number, because "real infrastructure made
    accuracy worse and left evidence alone" is a finding and "the suite got
    worse" is not.
    """
    suite = report.suite_score()
    return {name: suite.axis_rate(name) for name in SCORING_AXES}


def not_comparable(baseline: SuiteScore, current: SuiteScore) -> tuple[str, ...]:
    """Return the runs one side scored and the other did not.

    A real-run comparison has a failure mode the synthetic one does not: an
    experiment that was valid last release and invalid this one is absent from
    one of the two sides for a reason that is not a corpus change. Naming them
    is what lets the rest of the comparison be read.
    """
    before = {found.key for found in baseline.scenarios}
    after = {found.key for found in current.scenarios}
    return tuple(sorted(before ^ after))


def comparable_pairs(baseline: SuiteScore, current: SuiteScore) -> tuple[SuiteScore, SuiteScore]:
    """Return the two suite scores narrowed to the runs both of them scored.

    What makes cross-release comparison possible at all. Comparing the
    full sets would refuse whenever a single experiment misfired on either side,
    which over fourteen experiments is most releases.
    """
    shared = {found.key for found in baseline.scenarios} & {
        found.key for found in current.scenarios
    }
    return (
        _narrow(baseline, shared),
        _narrow(current, shared),
    )


def _narrow(suite: SuiteScore, keys: set[str]) -> SuiteScore:
    """Return ``suite`` holding only the scenarios in ``keys``."""
    scenarios = tuple(found for found in suite.scenarios if found.key in keys)
    return SuiteScore(
        scenarios=scenarios,
        label=suite.label,
        corpus_version=corpus_version(found.key for found in scenarios),
        duration_seconds=suite.duration_seconds,
        attempts_per_scenario=suite.attempts_per_scenario,
        axes=suite.axes,
    )


def report_of(
    runs: Sequence[RealRunScore],
    *,
    label: str = "",
    duration_seconds: float = 0.0,
    attempted: Sequence[str] = (),
) -> RealRunReport:
    """Return ``runs`` as one report."""
    return RealRunReport(
        runs=tuple(runs),
        label=label,
        duration_seconds=duration_seconds,
        attempted=tuple(attempted) or tuple(run.key for run in runs),
    )


__all__ = [
    "RealRunExpectation",
    "RealRunReport",
    "RealRunScore",
    "RunValidity",
    "axis_rates",
    "comparable_pairs",
    "not_comparable",
    "report_of",
    "score_real_run",
]
