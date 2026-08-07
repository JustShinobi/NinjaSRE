"""Enable a fault, investigate what it did, score it, turn it off.

The shape is the chaos runner's, and the reasons are the same, so the pieces are
the same pieces: the validity probe, the real-run scorer, and the report that
keeps an agent failure apart from an experiment failure. What differs is only
where the fault comes from and how it is removed.

One thing is genuinely different and worth stating. A chaos fault takes effect
in the kernel and is visible immediately; a feature flag has to reach every
service that reads it, and "the flag is set" is not the same claim as "the
service is failing". That gap is exactly what the validity probe closes, and it
is why turning the flag on and investigating straight away would produce a suite
that reports the agent as wrong whenever propagation was slow.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from config.constants.chaos import ALERT_FAULT_LABEL
from core.domain.alerts.normalisation import RawAlert
from core.state.types import TeamContext
from tests.chaos.framework.cluster import Cluster
from tests.chaos.framework.validity import Validity, ValidityVerdict, probe_validity
from tests.e2e.otel_demo.faults import DEMO_SUITE, DemoFault
from tests.e2e.otel_demo.injection import FlagdFaults, FlagError, injected
from tests.harness.investigator import Investigator
from tests.harness.realruns import (
    RealRunExpectation,
    RealRunReport,
    RealRunScore,
    RunValidity,
    report_of,
    score_real_run,
)

#: The label carrying the fault a generated alert belongs to.
FAULT_LABEL = ALERT_FAULT_LABEL


@dataclass(frozen=True, slots=True)
class DemoOutcome:
    """What one fault produced, including the reasons it produced nothing."""

    fault_id: str
    validity: ValidityVerdict | None = None
    score: RealRunScore | None = None
    restored: tuple[str, ...] = ()
    refused: str = ""
    duration_seconds: float = 0.0

    @property
    def ran(self) -> bool:
        """Return whether the fault was enabled and an investigation happened."""
        return not self.refused and self.score is not None

    @property
    def key(self) -> str:
        """Return the key this run is scored and compared under."""
        return f"{DEMO_SUITE}/{self.fault_id}"

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this outcome."""
        return {
            "fault": self.fault_id,
            "key": self.key,
            "ran": self.ran,
            "refused": self.refused,
            "restored": list(self.restored),
            "duration_seconds": round(self.duration_seconds, 3),
            "validity": self.validity.to_record() if self.validity is not None else None,
            "score": self.score.to_record() if self.score is not None else None,
        }


def expectation_of(fault: DemoFault) -> RealRunExpectation:
    """Return ``fault``'s declaration in the shape the scorer takes."""
    declared = fault.expectation
    return RealRunExpectation(
        key=fault.key,
        suite=DEMO_SUITE,
        scenario_id=fault.fault_id,
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


def alert_for(fault: DemoFault, *, at: datetime) -> RawAlert:
    """Return the alert the demo's own monitoring would raise for ``fault``.

    Built here rather than shipped per fault: the demo's alerts all have the
    same shape — a service, an error rate, a namespace — and five near-identical
    JSON documents would be five chances for one of them to drift.
    """
    return RawAlert(
        text="",
        payload={
            "receiver": "demo-oncall",
            "status": "firing",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "ServiceErrorRateHigh",
                        "severity": fault.expectation.severity,
                        "service": fault.service or "frontend",
                        "namespace": fault.namespace,
                        FAULT_LABEL: fault.fault_id,
                    },
                    "annotations": {
                        "summary": (
                            f"{fault.service or 'the frontend'} error rate is above its objective"
                        )
                    },
                    "startsAt": at.isoformat(),
                    "endsAt": "0001-01-01T00:00:00Z",
                }
            ],
        },
        source_hint="alertmanager",
        received_at=at if at.tzinfo is not None else at.replace(tzinfo=UTC),
    )


async def run_fault(
    fault: DemoFault,
    *,
    cluster: Cluster,
    faults: FlagdFaults,
    investigator: Investigator,
    run_id: str = "",
    now: datetime | None = None,
    **probe_options: Any,
) -> DemoOutcome:
    """Return the outcome of enabling ``fault`` and investigating what it did."""
    started = time.perf_counter()
    at = now if now is not None else datetime.now(UTC)

    try:
        with injected(faults, fault):
            alert = alert_for(fault, at=at)
            team = TeamContext(
                team_id=fault.expectation.team_id,
                integrations=fault.expectation.integrations,
                destinations=(),
            )
            live = await investigator.investigate(
                alert, team=team, run_id=f"otel-demo-{fault.fault_id}-{run_id}"
            )
            verdict = probe_validity(cluster, fault.expectation, **probe_options)
            score = score_real_run(
                expectation_of(fault),
                live.observation,
                validity=_validity_of(verdict),
                validity_detail=verdict.detail,
                run_id=live.run_id,
                alert=alert.payload,
            )
    except FlagError as failure:
        return DemoOutcome(
            fault_id=fault.fault_id,
            refused=str(failure),
            duration_seconds=time.perf_counter() - started,
        )

    return DemoOutcome(
        fault_id=fault.fault_id,
        validity=verdict,
        score=score,
        restored=(fault.flag,),
        duration_seconds=time.perf_counter() - started,
    )


async def run_faults(
    faults_to_run: Sequence[DemoFault],
    *,
    cluster: Cluster,
    faults: FlagdFaults,
    investigator: Investigator,
    run_id: str = "",
    label: str = DEMO_SUITE,
    now: datetime | None = None,
    **probe_options: Any,
) -> tuple[RealRunReport, tuple[DemoOutcome, ...]]:
    """Return every fault's outcome, scored, with each flag put back after it."""
    started = time.perf_counter()
    outcomes: list[DemoOutcome] = []
    scores: list[RealRunScore] = []

    for fault in faults_to_run:
        outcome = await run_fault(
            fault,
            cluster=cluster,
            faults=faults,
            investigator=investigator,
            run_id=run_id,
            now=now,
            **probe_options,
        )
        outcomes.append(outcome)
        if outcome.score is not None:
            scores.append(outcome.score)
        else:
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
        attempted=[fault.key for fault in faults_to_run],
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
    "FAULT_LABEL",
    "DemoOutcome",
    "alert_for",
    "expectation_of",
    "run_fault",
    "run_faults",
]
