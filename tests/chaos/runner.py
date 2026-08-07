"""One experiment, from lock to score to cleanup, and the same for fourteen.

The order is the whole design, and every step of it is a step that costs
something if it is skipped:

1. **Take the cluster's lock.** Two suites injecting faults into one cluster
   score each other's damage.
2. **Preflight.** An experiment run against an already-broken cluster measures
   the cluster.
3. **Inject**, registered for removal before it exists.
4. **Raise the alert** the fault would raise, through the pipeline's real entry
   point, so intake and normalisation are part of what is measured.
5. **Investigate** with the real integrations against live telemetry.
6. **Probe validity.** Did the fault actually bite? Everything after this
   depends on the answer, and getting it wrong turns a flaky cluster into an
   agent regression.
7. **Score** on the evaluation harness's five axes, and only if the run
   was valid.
8. **Clean up**, on every way out — including the ways that do not come back
   through this function at all.

Steps 1, 2, and 8 are the ones a person writing this in a hurry leaves out, and
they are the three that decide whether the suite can be run twice.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config.constants.chaos import CHAOS_LOCK_STALE_SECONDS
from core.state.types import TeamContext
from tests.chaos.framework.alerts import alert_for
from tests.chaos.framework.catalogue import Experiment
from tests.chaos.framework.cleanup import (
    CleanupLedger,
    CleanupReport,
    RunInterrupted,
    deferred_cleanup,
)
from tests.chaos.framework.cluster import Cluster
from tests.chaos.framework.injector import InjectionError, inject
from tests.chaos.framework.lock import ClusterBusy, cluster_lock
from tests.chaos.framework.preflight import PreflightReport, preflight
from tests.chaos.framework.validity import Validity, ValidityVerdict, probe_validity
from tests.harness.investigator import Investigator
from tests.harness.realruns import (
    RealRunExpectation,
    RealRunReport,
    RealRunScore,
    RunValidity,
    report_of,
    score_real_run,
)

#: The suite a chaos run is filed under, in a score and in a baseline.
CHAOS_SUITE = "chaos"


@dataclass(frozen=True, slots=True)
class ExperimentOutcome:
    """Everything one experiment produced, including the reasons it produced nothing."""

    experiment_id: str
    preflight: PreflightReport
    validity: ValidityVerdict | None = None
    score: RealRunScore | None = None
    cleanup: CleanupReport = field(default_factory=CleanupReport)
    alert_fired: bool = False
    refused: str = ""
    duration_seconds: float = 0.0

    @property
    def ran(self) -> bool:
        """Return whether the fault was injected and an investigation happened."""
        return not self.refused and self.alert_fired

    @property
    def key(self) -> str:
        """Return the key this run is scored and compared under."""
        return f"{CHAOS_SUITE}/{self.experiment_id}"

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this outcome."""
        return {
            "experiment": self.experiment_id,
            "key": self.key,
            "ran": self.ran,
            "refused": self.refused,
            "duration_seconds": round(self.duration_seconds, 3),
            "preflight": {
                "healthy": self.preflight.healthy,
                "reasons": list(self.preflight.reasons),
            },
            "validity": self.validity.to_record() if self.validity is not None else None,
            "score": self.score.to_record() if self.score is not None else None,
            "cleanup": {
                "removed": list(self.cleanup.removed),
                "swept": list(self.cleanup.swept),
                "failures": list(self.cleanup.failures),
                "baseline_restored": self.cleanup.baseline_restored,
            },
        }


def expectation_of(experiment: Experiment) -> RealRunExpectation:
    """Return ``experiment``'s declaration in the shape the scorer takes."""
    declared = experiment.expectation
    return RealRunExpectation(
        key=f"{CHAOS_SUITE}/{declared.experiment_id}",
        suite=CHAOS_SUITE,
        scenario_id=declared.experiment_id,
        failure_mode=declared.failure_mode,
        severity=declared.severity,
        difficulty=declared.difficulty,
        root_cause_category=declared.expected_root_cause_category,
        required_keywords=declared.required_keywords,
        equivalent_root_cause_categories=declared.equivalent_root_cause_categories,
        forbidden_categories=declared.forbidden_categories,
        required_evidence_sources=declared.required_evidence_sources,
        optimal_trajectory=declared.optimal_trajectory,
        max_investigation_loops=declared.max_investigation_loops,
        integrations=declared.integrations,
        available_evidence=declared.available_evidence,
        team_id=declared.team_id,
        title=declared.title,
    )


async def run_experiment(
    experiment: Experiment,
    *,
    cluster: Cluster,
    investigator: Investigator,
    run_id: str,
    now: datetime | None = None,
    **probe_options: Any,
) -> ExperimentOutcome:
    """Return the outcome of injecting ``experiment`` and investigating what it did.

    Raises:
        RunInterrupted: a signal arrived; the fault was removed before stopping.
    """
    started = time.perf_counter()
    at = now if now is not None else datetime.now(UTC)

    report = preflight(cluster)
    if not report.healthy:
        return ExperimentOutcome(
            experiment_id=experiment.experiment_id,
            preflight=report,
            refused=report.summary,
            duration_seconds=time.perf_counter() - started,
        )

    ledger = CleanupLedger()
    outcome: ExperimentOutcome | None = None

    with deferred_cleanup(cluster, ledger=ledger) as book:
        try:
            fault = inject(cluster, experiment, ledger=book, run_id=run_id)
        except InjectionError as failure:
            return ExperimentOutcome(
                experiment_id=experiment.experiment_id,
                preflight=report,
                refused=str(failure),
                duration_seconds=time.perf_counter() - started,
            )

        alert = alert_for(experiment, fault.record, at=at)
        team = TeamContext(
            team_id=experiment.expectation.team_id,
            integrations=experiment.expectation.integrations,
            destinations=(),
        )
        live = await investigator.investigate(
            alert, team=team, run_id=f"chaos-{experiment.experiment_id}-{run_id}"
        )

        verdict = probe_validity(cluster, experiment.expectation, **probe_options)
        score = score_real_run(
            expectation_of(experiment),
            live.observation,
            validity=_validity_of(verdict),
            validity_detail=verdict.detail,
            run_id=live.run_id,
            alert=alert.payload,
        )
        outcome = ExperimentOutcome(
            experiment_id=experiment.experiment_id,
            preflight=report,
            validity=verdict,
            score=score,
            alert_fired=True,
        )

    # The ledger's context manager has run cleanup by now, and its report is what
    # says whether the next experiment may start.
    final = clean_report(cluster, ledger)
    return ExperimentOutcome(
        experiment_id=outcome.experiment_id,
        preflight=outcome.preflight,
        validity=outcome.validity,
        score=outcome.score,
        cleanup=final,
        alert_fired=outcome.alert_fired,
        duration_seconds=time.perf_counter() - started,
    )


def clean_report(cluster: Cluster, ledger: CleanupLedger) -> CleanupReport:
    """Return what the cluster looks like after cleanup ran.

    Called after the deferred cleanup has already removed everything, so this is
    a verification rather than a second attempt — the numbers it reports are
    "nothing left" or the reason there is.
    """
    from tests.chaos.framework.cleanup import clean_up

    return clean_up(cluster, ledger)


async def run_suite(
    experiments: Sequence[Experiment],
    *,
    cluster: Cluster,
    investigator: Investigator,
    run_id: str,
    lock_root: Path,
    label: str = "chaos",
    stale_seconds: float = CHAOS_LOCK_STALE_SECONDS,
    now: datetime | None = None,
    **probe_options: Any,
) -> tuple[RealRunReport, tuple[ExperimentOutcome, ...]]:
    """Return every experiment's outcome, scored, with the cluster held throughout.

    The lock is taken once for the whole suite rather than per experiment. A
    per-experiment lock would let a second suite interleave between two
    experiments and inject into a cluster this one is about to preflight.

    Raises:
        ClusterBusy: another run holds this cluster.
        RunInterrupted: a signal arrived mid-suite; nothing is left applied.
    """
    started = time.perf_counter()
    outcomes: list[ExperimentOutcome] = []
    scores: list[RealRunScore] = []

    with cluster_lock(cluster.name, root=lock_root, run_id=run_id, stale_seconds=stale_seconds):
        for experiment in experiments:
            outcome = await run_experiment(
                experiment,
                cluster=cluster,
                investigator=investigator,
                run_id=run_id,
                now=now,
                **probe_options,
            )
            outcomes.append(outcome)
            if outcome.score is not None:
                scores.append(outcome.score)
            elif outcome.refused:
                scores.append(
                    RealRunScore(
                        key=outcome.key,
                        validity=RunValidity.UNKNOWN,
                        validity_detail=outcome.refused,
                    )
                )

    report = report_of(
        scores,
        label=label,
        duration_seconds=time.perf_counter() - started,
        attempted=[f"{CHAOS_SUITE}/{found.experiment_id}" for found in experiments],
    )
    return report, tuple(outcomes)


def _validity_of(verdict: ValidityVerdict) -> RunValidity:
    """Return the verdict as the scorer's own vocabulary."""
    if verdict.validity is Validity.VALID:
        return RunValidity.VALID
    if verdict.validity is Validity.INVALID:
        return RunValidity.INVALID
    return RunValidity.UNKNOWN


__all__ = [
    "CHAOS_SUITE",
    "ClusterBusy",
    "ExperimentOutcome",
    "RunInterrupted",
    "expectation_of",
    "run_experiment",
    "run_suite",
]
