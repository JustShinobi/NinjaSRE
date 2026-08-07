"""Investigations that did not happen, for asserting everything around one.

The chaos and end-to-end runners have a lot to get right that has nothing to do
with what the agent concluded: the lock, the preflight refusal, the order of
injection and registration, the validity gate, the cleanup on every exit. Driving
a real investigation to assert any of those would need a cluster and a provider,
which is the reason infrastructure code usually has no tests at all.

So the runner takes an ``Investigator`` and these satisfy it. What the scripted
one returns is a real ``Observation`` — the same value a live run produces and
the same one the five axes read — so a test that asserts "this run scored as an
agent failure" is asserting against the production scorer, not a stub of it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from config.constants.chaos import ALERT_ORIGIN_LABELS
from core.domain.alerts.normalisation import RawAlert
from core.state.types import TeamContext
from tests.harness.realruns import RealRunExpectation
from tests.harness.scoring.composite import Observation
from tests.harness.scoring.matching import steps_from_iterations


@dataclass(frozen=True, slots=True)
class ScriptedRun:
    """One investigation's worth of observation, with an identity."""

    observation: Observation
    run_id: str = "scripted"


@dataclass(slots=True)
class ScriptedInvestigator:
    """Answers each alert from a script, and keeps what it was asked.

    ``answers`` is consumed in order and the last one repeats, which is what
    lets a suite-level test say "every experiment concluded correctly" in one
    line and "the fourth one got it wrong" in two.
    """

    answers: Sequence[Observation]
    alerts: list[RawAlert] = field(default_factory=list)
    teams: list[TeamContext] = field(default_factory=list)
    position: int = 0

    async def investigate(
        self, alert: RawAlert, *, team: TeamContext, run_id: str = ""
    ) -> ScriptedRun:
        """Return the next scripted observation, recording the alert it answered."""
        self.alerts.append(alert)
        self.teams.append(team)
        index = min(self.position, len(self.answers) - 1)
        self.position += 1
        return ScriptedRun(observation=self.answers[index], run_id=run_id or "scripted")


@dataclass(slots=True)
class DerivedInvestigator:
    """Answers each alert by applying ``answer`` to the run's own expectation.

    The suite-level double. A fourteen-experiment assertion needs fourteen
    different correct answers, and writing them out would be writing the answer
    keys twice — which is how an assertion ends up agreeing with itself.
    """

    expectations: dict[str, RealRunExpectation]
    answer: Callable[[RealRunExpectation], Observation]
    alerts: list[RawAlert] = field(default_factory=list)

    async def investigate(
        self, alert: RawAlert, *, team: TeamContext, run_id: str = ""
    ) -> ScriptedRun:
        """Return the observation ``answer`` derives from this run's expectation."""
        self.alerts.append(alert)
        key = _experiment_of(alert)
        expectation = self.expectations[key]
        return ScriptedRun(observation=self.answer(expectation), run_id=run_id or key)


def correct_answer(expectation: RealRunExpectation) -> Observation:
    """Return the observation an investigation that got it right would produce."""
    return Observation(
        root_cause_category=expectation.root_cause_category,
        answer_text=" ".join(expectation.required_keywords),
        evidence_sources=expectation.required_evidence_sources or expectation.integrations,
        held_evidence_ids=frozenset({"e1"}),
        trajectory=steps_from_iterations(
            (index + 1, action) for index, action in enumerate(expectation.optimal_trajectory)
        ),
        iterations=max(len(expectation.optimal_trajectory), 1),
        tokens=4_000,
        duration_seconds=2.0,
        provider_id="scripted",
        model_id="scripted",
    )


def wrong_answer(expectation: RealRunExpectation) -> Observation:
    """Return the observation an investigation that missed would produce."""
    return Observation(
        root_cause_category="unknown",
        answer_text="nothing conclusive was established",
        evidence_sources=(),
        iterations=1,
        tokens=4_000,
        duration_seconds=2.0,
        provider_id="scripted",
        model_id="scripted",
    )


def _experiment_of(alert: RawAlert) -> str:
    """Return the run identifier the generated alert carries.

    Both suites label their alerts with what raised them — chaos with the
    experiment, the demo with the fault — and this double answers either, so a
    suite-level assertion reads the same in both.
    """
    for entry in (alert.payload or {}).get("alerts") or ():
        labels = entry.get("labels") or {}
        for label in ALERT_ORIGIN_LABELS:
            found = labels.get(label, "")
            if found:
                return str(found)
    return ""


__all__ = [
    "DerivedInvestigator",
    "ScriptedInvestigator",
    "ScriptedRun",
    "correct_answer",
    "wrong_answer",
]
