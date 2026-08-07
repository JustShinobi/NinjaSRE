"""The baseline, then one run of the same corpus per arm.

The runner's whole job is to keep everything except the arm identical. Same
scenarios, same order, same number of attempts, same scoring — and the switches
handed in per attempt rather than set anywhere, so there is no moment at which
one arm's configuration is reachable from another's run.

**What actually runs an attempt is injected.** The harness knows how to remove a
mechanism and how to score what comes back; it does not know how a deployment
composes a pipeline, and a runner that did would be a second composition root
drifting away from the real one. The caller supplies an ``ArmRunner``; the
synthetic proof scenario supplies one over the real loop, and a unit test
supplies a deterministic policy.

**A broken arm is a value, not an exception.** Eight arms is an expensive run,
and losing the other seven because the masking arm could not be configured would
mean nobody runs the full ablation twice. The failure is recorded on the arm, and
the report refuses to price a mechanism whose arm did not complete — which is the
half that matters, because an arm that silently reported "no measurable effect"
would be the worst possible outcome.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from config.constants.evaluation import DEFAULT_SCENARIO_ATTEMPTS, MAX_SCENARIO_ATTEMPTS
from tests.harness.ablation.config import AblationConfig, one_at_a_time
from tests.harness.ablation.switches import MechanismSwitches
from tests.harness.loader import Scenario
from tests.harness.scoring.composite import Observation, ScenarioScore, score_observation
from tests.harness.scoring.report import SuiteScore, corpus_version, summarise

#: How a caller runs one attempt at one scenario under one arm's configuration.
#: Returns what the attempt did rather than a score, because scoring belongs to
#: this harness and a caller that scored its own results could hand back a number
#: produced by a different rule than the baseline's.
ArmRunner = Callable[[Scenario, MechanismSwitches, int], Awaitable[Observation]]

#: Called as each arm finishes, so a long ablation can report progress without
#: the runner knowing what a progress report looks like.
ArmObserver = Callable[["ArmResult"], None]


@dataclass(frozen=True, slots=True)
class ArmResult:
    """One arm of an ablation: what it removed, what it scored, how it was configured."""

    config: AblationConfig
    suite: SuiteScore = field(default_factory=SuiteScore)
    configuration: Mapping[str, Any] = field(default_factory=dict)
    failure: str = ""
    duration_seconds: float = 0.0

    @property
    def completed(self) -> bool:
        """Return whether this arm produced a result at all."""
        return not self.failure

    @property
    def mechanism_label(self) -> str:
        """Return the name this arm is priced under in a report.

        The mechanisms it removed, joined — not the arm's own name. Two files
        that disable the same mechanism are the same experiment, and a table keyed
        on the arm name would show it twice under two headings.
        """
        return "+".join(self.config.disabled)

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this arm."""
        return {
            "name": self.config.name,
            "disabled": list(self.config.disabled),
            "description": self.config.description,
            "configuration": dict(self.configuration),
            "failure": self.failure,
            "duration_seconds": round(self.duration_seconds, 3),
            "suite": self.suite.to_record(),
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> ArmResult:
        """Return the arm a stored record describes."""
        return cls(
            config=AblationConfig(
                name=str(record["name"]),
                disabled=tuple(str(item) for item in record.get("disabled") or ()),
                description=str(record.get("description", "")),
            ),
            suite=SuiteScore.from_record(record.get("suite") or {}),
            configuration=dict(record.get("configuration") or {}),
            failure=str(record.get("failure", "")),
            duration_seconds=float(record.get("duration_seconds", 0.0)),
        )


@dataclass(frozen=True, slots=True)
class AblationResult:
    """Every arm of one ablation, baseline first."""

    arms: tuple[ArmResult, ...] = ()
    corpus_version: str = ""
    attempts_per_scenario: int = DEFAULT_SCENARIO_ATTEMPTS

    @property
    def baseline(self) -> ArmResult:
        """Return the arm every other one is measured against.

        Raises:
            ValueError: no baseline arm ran, which makes every delta meaningless.
        """
        for arm in self.arms:
            if arm.config.is_baseline:
                return arm
        raise ValueError(
            "this ablation has no baseline arm, so there is nothing to subtract from; "
            "every contribution it could report would be a bare pass rate wearing a delta's name"
        )

    def arm(self, name: str) -> ArmResult | None:
        """Return the arm called ``name``, or ``None``."""
        return next((found for found in self.arms if found.config.name == name), None)

    @property
    def failed_arms(self) -> tuple[ArmResult, ...]:
        """Return the arms that did not complete."""
        return tuple(arm for arm in self.arms if not arm.completed)

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this ablation."""
        return {
            "corpus_version": self.corpus_version,
            "attempts_per_scenario": self.attempts_per_scenario,
            "arms": [arm.to_record() for arm in self.arms],
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> AblationResult:
        """Return the ablation a stored record describes."""
        return cls(
            arms=tuple(ArmResult.from_record(item) for item in record.get("arms") or ()),
            corpus_version=str(record.get("corpus_version", "")),
            attempts_per_scenario=int(
                record.get("attempts_per_scenario", DEFAULT_SCENARIO_ATTEMPTS)
            ),
        )


async def run_ablation(
    scenarios: Sequence[Scenario],
    *,
    arm: ArmRunner,
    configs: Sequence[AblationConfig] = (),
    attempts: int = DEFAULT_SCENARIO_ATTEMPTS,
    base: MechanismSwitches | None = None,
    observer: ArmObserver | None = None,
) -> AblationResult:
    """Return one result per arm over ``scenarios``, the baseline first.

    Arms run in sequence, and so do attempts within them. The corpus is small,
    and concurrency here would make the cost axis — one of the five — depend on
    how many cores the machine that ran it had.

    Raises:
        ValueError: ``attempts`` is outside the bound Article II sets on it.
    """
    if not 1 <= attempts <= MAX_SCENARIO_ATTEMPTS:
        raise ValueError(f"attempts must be between 1 and {MAX_SCENARIO_ATTEMPTS}, got {attempts}")

    wanted = tuple(configs) if configs else one_at_a_time()
    version = corpus_version(found.key for found in scenarios)

    results: list[ArmResult] = []
    for config in wanted:
        result = await _run_arm(
            config, scenarios, arm=arm, attempts=attempts, base=base, version=version
        )
        results.append(result)
        if observer is not None:
            observer(result)

    return AblationResult(
        arms=tuple(results), corpus_version=version, attempts_per_scenario=attempts
    )


async def _run_arm(
    config: AblationConfig,
    scenarios: Sequence[Scenario],
    *,
    arm: ArmRunner,
    attempts: int,
    base: MechanismSwitches | None,
    version: str,
) -> ArmResult:
    """Return one arm's result, or the arm carrying the reason it has none."""
    switches = config.switches(base)
    started = time.perf_counter()
    scores: list[ScenarioScore] = []

    try:
        for scenario in scenarios:
            for attempt in range(1, attempts + 1):
                observation = await arm(scenario, switches, attempt)
                scores.append(score_observation(scenario, observation, attempt=attempt))
    except Exception as error:  # noqa: BLE001 — one broken arm must not cost the others
        return ArmResult(
            config=config,
            configuration=switches.trace_summary(),
            failure=f"{type(error).__name__}: {error}",
            duration_seconds=time.perf_counter() - started,
        )

    elapsed = time.perf_counter() - started
    return ArmResult(
        config=config,
        suite=summarise(
            scores,
            label=config.name,
            corpus_version=version,
            duration_seconds=elapsed,
        ),
        configuration=switches.trace_summary(),
        duration_seconds=elapsed,
    )


__all__ = [
    "AblationResult",
    "ArmObserver",
    "ArmResult",
    "ArmRunner",
    "run_ablation",
]
