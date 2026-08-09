"""Many scores, aggregated — and the aggregate's inability to hide the one case.

An aggregate is a compression, and every compression loses something. The thing
this one may never lose is a scenario that went from proposing the correct action
to proposing a harmful one. That change can happen while the total improves — six
scenarios start passing, one learns to hard-stop a running guest — and a report
that showed only the total would call that an improvement and be believed.

So ``compare`` returns three findings and not a number: the scenarios that
stopped passing, the scenarios whose action became harmful, and the movement in
the rate. Any of the first two is a regression whatever the third says.

The per-arm and per-model views are here for the same reason the aggregate is
not enough. "Memory helps" and "the self-hosted model is usable" are both claims
with a number behind them, and the number is a difference between two cells of
this report rather than an opinion about the corpus.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from config.constants.hypervisor_scenarios import (
    HYPERVISOR_REGRESSION_TOLERANCE,
    SCENARIO_ABLATION_ARMS,
    SCENARIO_MODE_FIXTURE,
    SCENARIO_MODEL_PROFILES,
)
from tests.harness.proxmox.declaration import Scenario
from tests.harness.proxmox.readings import Readings
from tests.harness.proxmox.scoring import ScenarioScore, score
from tests.harness.proxmox.transcripts import RecordedRun
from tests.harness.proxmox.verdicts import ActionVerdict, CompletionVerdict


@dataclass(frozen=True, slots=True)
class CellReport:
    """One model under one ablation arm, over every scenario it was run on."""

    model: str
    arm: str
    scored: int = 0
    passes: int = 0
    harmful: int = 0
    incomplete: int = 0

    @property
    def pass_rate(self) -> float:
        """Return the share of this cell's scenarios that passed."""
        return self.passes / self.scored if self.scored else 0.0

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form the baseline stores."""
        return {
            "model": self.model,
            "arm": self.arm,
            "scored": self.scored,
            "passes": self.passes,
            "harmful": self.harmful,
            "incomplete": self.incomplete,
            "pass_rate": round(self.pass_rate, 4),
        }


@dataclass(frozen=True, slots=True)
class Movement:
    """One scenario-and-cell whose verdict changed between two runs."""

    scenario_id: str
    model: str
    arm: str
    was: str
    now: str
    reasoning: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()

    def describe(self) -> str:
        """Return the block a failing gate prints: what moved, and on what evidence."""
        lines = [f"{self.scenario_id} [{self.model}/{self.arm}]: {self.was} -> {self.now}"]
        lines.extend(f"    {line}" for line in self.reasoning)
        if self.readings:
            lines.append("    readings:")
            lines.extend(f"      {line}" for line in self.readings)
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class Comparison:
    """What changed between a stored baseline and the run in front of you."""

    became_harmful: tuple[Movement, ...] = ()
    stopped_passing: tuple[Movement, ...] = ()
    started_passing: tuple[Movement, ...] = ()
    missing_from_run: tuple[str, ...] = ()
    rate_before: float = 0.0
    rate_after: float = 0.0

    @property
    def rate_movement(self) -> float:
        """Return how far the aggregate moved, positive for an improvement."""
        return self.rate_after - self.rate_before

    @property
    def is_regression(self) -> bool:
        """Return whether this run is worse than the baseline in any way that counts.

        A harmful transition is a regression on its own, whatever the aggregate
        did. That is the whole point: the aggregate is allowed to improve and the
        answer is still no.
        """
        return bool(
            self.became_harmful
            or self.stopped_passing
            or self.missing_from_run
            or self.rate_movement < -HYPERVISOR_REGRESSION_TOLERANCE
        )

    def describe(self) -> str:
        """Return everything a reviewer needs, without re-running the suite."""
        blocks: list[str] = []
        if self.became_harmful:
            blocks.append(
                "actions that became harmful:\n"
                + "\n".join(found.describe() for found in self.became_harmful)
            )
        if self.stopped_passing:
            blocks.append(
                "scenarios that stopped passing:\n"
                + "\n".join(found.describe() for found in self.stopped_passing)
            )
        if self.missing_from_run:
            blocks.append(f"scenarios in the baseline and not in this run: {self.missing_from_run}")
        blocks.append(
            f"pass rate {self.rate_before:.4f} -> {self.rate_after:.4f} "
            f"({self.rate_movement:+.4f}); tolerance {HYPERVISOR_REGRESSION_TOLERANCE}"
        )
        return "\n\n".join(blocks)


@dataclass(frozen=True, slots=True)
class SuiteReport:
    """Every score a run produced, per scenario and aggregated."""

    scores: tuple[ScenarioScore, ...] = ()
    duration_seconds: float = 0.0

    @property
    def total(self) -> int:
        """Return how many scenario-and-cell scores this run produced."""
        return len(self.scores)

    @property
    def passes(self) -> int:
        """Return how many of them passed on every axis."""
        return sum(1 for found in self.scores if found.passed)

    @property
    def pass_rate(self) -> float:
        """Return the share that passed."""
        return self.passes / self.total if self.total else 0.0

    @property
    def harmful(self) -> tuple[ScenarioScore, ...]:
        """Return every score whose proposed action would have made things worse."""
        return tuple(found for found in self.scores if found.harmful)

    @property
    def incomplete(self) -> tuple[ScenarioScore, ...]:
        """Return every score where the model could not finish, which is not a wrong answer."""
        return tuple(
            found for found in self.scores if found.completion is CompletionVerdict.INCOMPLETE
        )

    @property
    def scenarios(self) -> tuple[ScenarioScore, ...]:
        """Return the scores in report order: domain, then scenario, then cell."""
        return tuple(
            sorted(self.scores, key=lambda found: (found.domain, found.scenario_id, found.cell))
        )

    @property
    def scenario_ids(self) -> tuple[str, ...]:
        """Return every scenario this run scored, once, in name order."""
        return tuple(sorted({found.scenario_id for found in self.scores}))

    def cells(self) -> tuple[CellReport, ...]:
        """Return one report per model-and-arm present, in declared order."""
        grouped: dict[tuple[str, str], list[ScenarioScore]] = {}
        for found in self.scores:
            grouped.setdefault((found.model, found.arm), []).append(found)
        ordered = sorted(
            grouped.items(),
            key=lambda item: (
                _index(SCENARIO_MODEL_PROFILES, item[0][0]),
                _index(SCENARIO_ABLATION_ARMS, item[0][1]),
            ),
        )
        return tuple(
            CellReport(
                model=model,
                arm=arm,
                scored=len(found),
                passes=sum(1 for one in found if one.passed),
                harmful=sum(1 for one in found if one.harmful),
                incomplete=sum(
                    1 for one in found if one.completion is CompletionVerdict.INCOMPLETE
                ),
            )
            for (model, arm), found in ordered
        )

    def cell(self, *, model: str, arm: str) -> CellReport:
        """Return the report for one model-and-arm, or an empty one.

        Never raises. Asking about a cell nobody ran is a legitimate question
        with the answer "nothing", and an exception would put a guard at every
        call site of an ablation report.
        """
        for found in self.cells():
            if found.model == model and found.arm == arm:
                return found
        return CellReport(model=model, arm=arm)

    def modes(self) -> dict[str, tuple[str, ...]]:
        """Return which scenarios ran simulated and which ran against a cluster.

        FR-004 asks the suite to state this, and stating it per scenario rather
        than as a count is what lets a release note say which of the destructive
        ones were actually destroyed.
        """
        grouped: dict[str, set[str]] = {}
        for found in self.scores:
            grouped.setdefault(found.mode, set()).add(found.scenario_id)
        return {mode: tuple(sorted(names)) for mode, names in sorted(grouped.items())}

    def to_record(self) -> dict[str, Any]:
        """Return the document a baseline is stored as and a comparison reads."""
        return {
            "total": self.total,
            "passes": self.passes,
            "pass_rate": round(self.pass_rate, 4),
            "harmful": len(self.harmful),
            "incomplete": len(self.incomplete),
            "modes": {mode: list(names) for mode, names in self.modes().items()},
            "cells": [found.to_record() for found in self.cells()],
            "scenarios": [found.to_record() for found in self.scenarios],
        }

    def compare(self, baseline: Mapping[str, Any]) -> Comparison:
        """Return what moved between ``baseline`` and this run."""
        before = {_key(entry): entry for entry in baseline.get("scenarios", ())}
        after = {_key(entry.to_record()): entry for entry in self.scores}

        became_harmful: list[Movement] = []
        stopped: list[Movement] = []
        started: list[Movement] = []
        for key, stored in before.items():
            current = after.get(key)
            if current is None:
                continue
            was_harmful = stored.get("action") == ActionVerdict.HARMFUL.value
            if current.harmful and not was_harmful:
                became_harmful.append(_movement(current, stored.get("action", "")))
            if stored.get("passed") and not current.passed:
                stopped.append(_movement(current, "passed"))
            if not stored.get("passed") and current.passed:
                started.append(_movement(current, "failed"))

        return Comparison(
            became_harmful=tuple(became_harmful),
            stopped_passing=tuple(stopped),
            started_passing=tuple(started),
            missing_from_run=tuple(sorted(key[0] for key in before if key not in after)),
            rate_before=float(baseline.get("pass_rate", 0.0)),
            rate_after=self.pass_rate,
        )


def _index(order: Sequence[str], value: str) -> int:
    """Return where ``value`` sits in ``order``, or the end when it is not in it."""
    return order.index(value) if value in order else len(order)


def _key(record: Mapping[str, Any]) -> tuple[str, str, str]:
    """Return the identity a score is compared across runs by."""
    return (
        str(record.get("scenario", "")),
        str(record.get("model", "")),
        str(record.get("arm", "")),
    )


def _movement(current: ScenarioScore, was: str) -> Movement:
    """Return ``current`` as a movement away from ``was``, readings included."""
    return Movement(
        scenario_id=current.scenario_id,
        model=current.model,
        arm=current.arm,
        was=was or "absent from the baseline",
        now=current.action.value if was != "passed" else "failed",
        reasoning=current.reasoning,
        readings=(
            tuple(entry.text for entry in current.readings.entries)
            if current.readings is not None
            else ()
        ),
    )


def report_for(
    attempts: Sequence[tuple[Scenario, RecordedRun]],
    *,
    readings: Mapping[str, Readings] | None = None,
    mode: str = SCENARIO_MODE_FIXTURE,
    duration_seconds: float = 0.0,
) -> SuiteReport:
    """Return every ``(scenario, run)`` pair scored, aggregated."""
    taken = readings or {}
    return SuiteReport(
        scores=tuple(
            score(scenario, run, readings=taken.get(scenario.scenario_id), mode=mode)
            for scenario, run in attempts
        ),
        duration_seconds=duration_seconds,
    )


def report_of(scores: Sequence[ScenarioScore], *, duration_seconds: float = 0.0) -> SuiteReport:
    """Return a report over scores somebody else produced."""
    return SuiteReport(scores=tuple(scores), duration_seconds=duration_seconds)


__all__ = [
    "CellReport",
    "Comparison",
    "Movement",
    "SuiteReport",
    "report_for",
    "report_of",
]
