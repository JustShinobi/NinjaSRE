"""Provision, break, investigate, score, destroy — and report what it cost.

The order matters in the same way the chaos runner's does, with one addition
that has no counterpart there: **the cost is reported whether or not anything
else worked**. A run that failed to provision still spent whatever it created
before it gave up, and a suite that only reported cost on success would be
silent about exactly the runs that leak.

Teardown is deferred rather than sequential, so the destroy happens on every way
out of the block — including the signalled one, where the alternative is a stack
that outlives the run and a bill that keeps arriving. The tag sweep behind it
covers the way out that runs no code at all.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from config.constants.chaos import ALERT_SCENARIO_LABEL
from core.domain.alerts.normalisation import RawAlert
from core.state.types import TeamContext
from tests.chaos.framework.cluster import SymptomSource
from tests.chaos.framework.validity import Validity, ValidityVerdict, probe_validity
from tests.e2e.cloud.cost import CostReport, SuiteCostReport, report_cost
from tests.e2e.cloud.provisioning import (
    Provisioner,
    ProvisioningError,
    StackPlan,
    deferred_teardown,
)
from tests.e2e.cloud.reaper import leaked
from tests.e2e.cloud.scenarios import CLOUD_SUITE, CloudScenario
from tests.harness.investigator import Investigator
from tests.harness.realruns import (
    RealRunExpectation,
    RealRunReport,
    RealRunScore,
    RunValidity,
    report_of,
    score_real_run,
)

#: The label carrying the scenario a generated alert belongs to.
SCENARIO_LABEL = ALERT_SCENARIO_LABEL


@dataclass(frozen=True, slots=True)
class CloudOutcome:
    """What one cloud scenario produced, and what it cost either way."""

    scenario_id: str
    cost: CostReport
    validity: ValidityVerdict | None = None
    score: RealRunScore | None = None
    provisioned: tuple[str, ...] = field(default_factory=tuple)
    destroyed: tuple[str, ...] = field(default_factory=tuple)
    leaked: tuple[str, ...] = field(default_factory=tuple)
    refused: str = ""

    @property
    def ran(self) -> bool:
        """Return whether the infrastructure came up and was investigated."""
        return not self.refused and self.score is not None

    @property
    def key(self) -> str:
        """Return the key this run is scored and compared under."""
        return f"{CLOUD_SUITE}/{self.scenario_id}"

    @property
    def clean(self) -> bool:
        """Return whether the account holds nothing left over from this run."""
        return not self.leaked

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this outcome."""
        return {
            "scenario": self.scenario_id,
            "key": self.key,
            "ran": self.ran,
            "refused": self.refused,
            "provisioned": list(self.provisioned),
            "destroyed": list(self.destroyed),
            "leaked": list(self.leaked),
            "clean": self.clean,
            "cost": self.cost.to_record(),
            "validity": self.validity.to_record() if self.validity is not None else None,
            "score": self.score.to_record() if self.score is not None else None,
        }


def expectation_of(scenario: CloudScenario) -> RealRunExpectation:
    """Return ``scenario``'s declaration in the shape the scorer takes."""
    declared = scenario.expectation
    return RealRunExpectation(
        key=scenario.key,
        suite=CLOUD_SUITE,
        scenario_id=scenario.scenario_id,
        failure_mode=declared.failure_mode,
        severity=declared.severity,
        difficulty=declared.difficulty,
        root_cause_category=declared.expected_root_cause_category,
        required_keywords=declared.required_keywords,
        forbidden_categories=declared.forbidden_categories,
        required_evidence_sources=declared.required_evidence_sources,
        optimal_trajectory=declared.optimal_trajectory,
        max_investigation_loops=declared.max_investigation_loops,
        integrations=declared.integrations,
        available_evidence=declared.available_evidence,
        team_id=declared.team_id,
        title=declared.title,
    )


def alert_for(scenario: CloudScenario, *, run_id: str, at: datetime) -> RawAlert:
    """Return the alert the provider's own monitoring would raise for ``scenario``."""
    return RawAlert(
        text="",
        payload={
            "receiver": "cloud-oncall",
            "status": "firing",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": f"{scenario.service}Degraded",
                        "severity": scenario.expectation.severity,
                        "service": scenario.service,
                        "region": scenario.region,
                        SCENARIO_LABEL: scenario.scenario_id,
                        "ninjasre_run": run_id,
                    },
                    "annotations": {"summary": scenario.expectation.title},
                    "startsAt": at.isoformat(),
                    "endsAt": "0001-01-01T00:00:00Z",
                }
            ],
        },
        source_hint="alertmanager",
        received_at=at if at.tzinfo is not None else at.replace(tzinfo=UTC),
    )


async def run_scenario(
    scenario: CloudScenario,
    *,
    provisioner: Provisioner,
    signals: SymptomSource,
    investigator: Investigator,
    run_id: str,
    now: datetime | None = None,
    **probe_options: Any,
) -> CloudOutcome:
    """Return the outcome of provisioning ``scenario``, breaking it, and tearing it down.

    Raises:
        RunInterrupted: a signal arrived; the stack was destroyed first.
    """
    started = time.perf_counter()
    at = now if now is not None else datetime.now(UTC)
    plan = StackPlan(
        scenario_id=scenario.scenario_id,
        run_id=run_id,
        module=scenario.module,
        variables=scenario.variables,
        region=scenario.region,
        at=at,
    )

    provisioned: tuple[str, ...] = ()
    verdict: ValidityVerdict | None = None
    score: RealRunScore | None = None
    refused = ""

    with deferred_teardown(provisioner, plan) as teardown:
        try:
            created = provisioner.apply(plan)
            provisioned = tuple(sorted(resource.identifier for resource in created))
        except ProvisioningError as failure:
            refused = str(failure)
        else:
            alert = alert_for(scenario, run_id=run_id, at=at)
            team = TeamContext(
                team_id=scenario.expectation.team_id,
                integrations=scenario.expectation.integrations,
                destinations=(),
            )
            live = await investigator.investigate(
                alert, team=team, run_id=f"cloud-{scenario.scenario_id}-{run_id}"
            )
            verdict = probe_validity(signals, scenario.expectation, **probe_options)
            score = score_real_run(
                expectation_of(scenario),
                live.observation,
                validity=_validity_of(verdict),
                validity_detail=verdict.detail,
                run_id=live.run_id,
                alert=alert.payload,
            )

    duration = time.perf_counter() - started
    return CloudOutcome(
        scenario_id=scenario.scenario_id,
        destroyed=tuple(sorted(set(teardown.destroyed))),
        cost=report_cost(
            scenario.scenario_id,
            scenario.resources,
            duration_seconds=duration,
            bound_usd=scenario.bound_usd,
        ),
        validity=verdict,
        score=score,
        provisioned=provisioned,
        leaked=_leaked(provisioner, run_id),
        refused=refused,
    )


async def run_scenarios(
    scenarios: Sequence[CloudScenario],
    *,
    provisioner: Provisioner,
    signals: SymptomSource,
    investigator: Investigator,
    run_id: str,
    label: str = CLOUD_SUITE,
    now: datetime | None = None,
    **probe_options: Any,
) -> tuple[RealRunReport, SuiteCostReport, tuple[CloudOutcome, ...]]:
    """Return every scenario's outcome, its score, and what the whole run cost."""
    started = time.perf_counter()
    outcomes: list[CloudOutcome] = []
    scores: list[RealRunScore] = []

    for scenario in scenarios:
        outcome = await run_scenario(
            scenario,
            provisioner=provisioner,
            signals=signals,
            investigator=investigator,
            run_id=run_id,
            now=now,
            **probe_options,
        )
        outcomes.append(outcome)
        scores.append(
            outcome.score
            if outcome.score is not None
            else RealRunScore(
                key=outcome.key,
                validity=RunValidity.UNKNOWN,
                validity_detail=outcome.refused,
            )
        )

    report = report_of(
        scores,
        label=label,
        duration_seconds=time.perf_counter() - started,
        attempted=[scenario.key for scenario in scenarios],
    )
    return report, SuiteCostReport(reports=tuple(found.cost for found in outcomes)), tuple(outcomes)


def _leaked(provisioner: Provisioner, run_id: str) -> tuple[str, ...]:
    """Return what this run left behind, or nothing when the account cannot be read."""
    try:
        return leaked(provisioner, run_id=run_id)
    except ProvisioningError:
        return ()


def _validity_of(verdict: ValidityVerdict) -> RunValidity:
    """Return the verdict as the scorer's own vocabulary."""
    if verdict.validity is Validity.VALID:
        return RunValidity.VALID
    if verdict.validity is Validity.INVALID:
        return RunValidity.INVALID
    return RunValidity.UNKNOWN


__all__ = [
    "SCENARIO_LABEL",
    "CloudOutcome",
    "alert_for",
    "expectation_of",
    "run_scenario",
    "run_scenarios",
]
