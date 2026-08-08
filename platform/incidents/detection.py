"""Turning one tick's verdicts into incidents, and closing the ones that cleared.

The bridge between observation and the lifecycle, and the place the two rules
that decide how many incidents exist actually live.

**Findings are grouped before anything is raised.** Fifty resources firing one
detector produce one correlation key, so one incident with fifty subjects is
raised rather than fifty incidents that a downstream deduplicator then has to
undo. Correlation is a property of the raise, not a cleanup afterwards.

**An incident closes when every one of its subjects has cleared.** Not when the
first one does. An incident about a node and its twenty guests is not resolved
because one guest recovered, and a close that fired on the first clear would
teach an operator that "resolved" means "partly".

The recovery duration is already inside the verdict: the evaluator only returns
``CLEAR`` when the recovery condition has held for the window the detector
declares. That is why nothing here counts anything — the duration is a property
of the window, and duplicating it would be a second place for it to be wrong.

**A detector that could not be evaluated gets its own incident,** in its own
correlation namespace, so "the disk detector is broken" and "the disk is full"
never correlate onto each other.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from platform.incidents import correlation
from platform.incidents.lifecycle import IncidentLifecycle, IncidentRaise
from platform.observability.logging import get_logger
from platform.observation.detectors.conditions import Observation, Verdict
from platform.observation.detectors.model import DetectorDeclaration
from platform.observation.evaluation import DetectorFailure, TickOutcome
from platform.observation.suppression import Suppression
from platform.persistence.ports.estate_repository import Resource
from platform.persistence.ports.incident_store import (
    Incident,
    IncidentOrigin,
    IncidentSubject,
)

logger = get_logger(__name__)

#: The severity an incident about a broken detector gets. High rather than
#: critical: the estate may be perfectly healthy, and the thing that is wrong is
#: that we cannot tell. High rather than medium for the same reason.
DETECTOR_FAILURE_SEVERITY = "high"


@dataclass(frozen=True, slots=True)
class IntakeReport:
    """What one tick's verdicts did to the incident list."""

    opened: tuple[Incident, ...] = ()
    correlated: tuple[Incident, ...] = ()
    closed: tuple[Incident, ...] = ()
    failures: tuple[Incident, ...] = ()
    #: Findings something covered, recorded as suppressed incidents rather than
    #: dropped — so "nothing happened because of this rule" is countable.
    suppressed: tuple[Incident, ...] = ()

    @property
    def live(self) -> tuple[Incident, ...]:
        """Return every incident this tick opened or added to."""
        return self.opened + self.correlated


@dataclass(frozen=True, slots=True)
class DetectionIntake:
    """One tick's outcome, absorbed into the incident list."""

    lifecycle: IncidentLifecycle
    #: The detectors that produced the outcome, by identifier. Needed because a
    #: verdict names its detector and the grouping key lives on the declaration.
    detectors: Mapping[str, DetectorDeclaration] = field(default_factory=dict)

    async def absorb(
        self,
        outcome: TickOutcome,
        *,
        resources: Sequence[Resource] = (),
        now: datetime,
    ) -> IntakeReport:
        """Raise, correlate, and close, and report what happened to each."""
        estate = {resource.resource_id: resource for resource in resources}

        opened: list[Incident] = []
        correlated: list[Incident] = []
        for key, findings in self._grouped(outcome.findings, estate).items():
            detector = self.detectors[findings[0].detector_id]
            before = await self.lifecycle.store.open_for(key)
            incident = await self.lifecycle.raise_incident(
                _raise_for(detector, key, findings), now=now
            )
            (correlated if before is not None else opened).append(incident)

        closed = await self._close_recovered(outcome, estate, now=now)
        failures = await self._raise_failures(outcome.failures, now=now)
        suppressed = await self._record_suppressions(outcome.suppressed, estate, now=now)

        return IntakeReport(
            opened=tuple(opened),
            correlated=tuple(correlated),
            closed=tuple(closed),
            failures=tuple(failures),
            suppressed=tuple(suppressed),
        )

    async def _record_suppressions(
        self,
        suppressions: Sequence[Suppression],
        estate: Mapping[str, Resource],
        *,
        now: datetime,
    ) -> list[Incident]:
        """Raise each suppressed finding as an incident, and close it as suppressed.

        Raised *and then* closed rather than dropped. FR-020 asks that
        suppression be recorded and never silent, and the honest way to record
        it is in the incident list, where an operator asking "why did nothing
        happen" already looks and where a rule that is too broad becomes a
        number rather than an absence.
        """
        grouped: dict[str, list[Suppression]] = {}
        for suppression in suppressions:
            detector = self.detectors.get(suppression.detector_id)
            if detector is None:  # pragma: no cover — the tick owns both lists
                continue
            key = correlation.for_detector(
                detector,
                estate.get(suppression.resource_id),
                resource_id=suppression.resource_id,
            )
            grouped.setdefault(key, []).append(suppression)

        recorded: list[Incident] = []
        for key, group in grouped.items():
            detector = self.detectors[group[0].detector_id]
            incident = await self.lifecycle.raise_incident(
                IncidentRaise(
                    correlation_key=f"{key}:suppressed",
                    title=f"{detector.name} (suppressed)",
                    summary=group[0].summary,
                    origin=IncidentOrigin.DETECTOR,
                    origin_id=detector.detector_id,
                    severity=detector.severity.value,
                    subjects=tuple(
                        IncidentSubject(
                            resource_id=suppression.resource_id,
                            detail=suppression.reason,
                            evidence={"suppressed_by": suppression.rule_id},
                            observed_at=suppression.at,
                        )
                        for suppression in group
                    ),
                    team_node_id=detector.team_node_id,
                    cause=group[0].reason,
                ),
                now=now,
            )
            recorded.append(
                await self.lifecycle.suppress(
                    incident.incident_id,
                    by=group[0].rule_id,
                    reason=group[0].reason,
                    now=now,
                )
            )
        return recorded

    def _grouped(
        self,
        observations: Sequence[Observation],
        estate: Mapping[str, Resource],
    ) -> dict[str, list[Observation]]:
        """Return the observations by the correlation key their detector implies."""
        grouped: dict[str, list[Observation]] = {}
        for observation in observations:
            detector = self.detectors.get(observation.detector_id)
            if detector is None:
                # A verdict from a detector that has since been reconfigured
                # away. Dropping it is right: raising an incident whose detector
                # nobody can look up would be an incident nobody can act on.
                logger.warning(
                    "incidents.finding_without_detector",
                    detector_id=observation.detector_id,
                )
                continue
            key = correlation.for_detector(
                detector,
                estate.get(observation.resource_id),
                resource_id=observation.resource_id,
            )
            grouped.setdefault(key, []).append(observation)
        return grouped

    async def _close_recovered(
        self,
        outcome: TickOutcome,
        estate: Mapping[str, Resource],
        *,
        now: datetime,
    ) -> list[Incident]:
        """Close the incidents whose every subject has cleared."""
        cleared_by_key = self._grouped(outcome.cleared, estate)
        still_firing = set(self._grouped(outcome.findings, estate))

        closed: list[Incident] = []
        for key, observations in cleared_by_key.items():
            if key in still_firing:
                continue
            incident = await self.lifecycle.store.open_for(key)
            if incident is None:
                continue
            recovered = {entry.resource_id for entry in observations}
            if not set(incident.subject_ids) <= recovered:
                # Some subject has not cleared. An incident about a node and its
                # twenty guests is not resolved because one guest recovered.
                continue
            closed.append(
                await self.lifecycle.self_close(
                    incident.incident_id,
                    cause=observations[0].detail
                    or "the recovery condition held for its declared duration",
                    now=now,
                )
            )
        return closed

    async def _raise_failures(
        self, failures: Sequence[DetectorFailure], *, now: datetime
    ) -> list[Incident]:
        """Raise one incident per detector that could not be evaluated."""
        by_detector: dict[str, list[DetectorFailure]] = {}
        for failure in failures:
            by_detector.setdefault(failure.detector_id, []).append(failure)

        raised: list[Incident] = []
        for detector_id, group in by_detector.items():
            first = group[0]
            raised.append(
                await self.lifecycle.raise_incident(
                    IncidentRaise(
                        correlation_key=correlation.for_detector_failure(detector_id),
                        title=f"Detector {detector_id} cannot be evaluated",
                        summary=first.summary,
                        origin=IncidentOrigin.DETECTOR,
                        origin_id=detector_id,
                        severity=DETECTOR_FAILURE_SEVERITY,
                        subjects=tuple(
                            IncidentSubject(
                                resource_id=failure.resource_id or detector_id,
                                detail=failure.reason,
                                evidence={"detector": detector_id},
                                observed_at=failure.failed_at,
                            )
                            for failure in group
                        ),
                        cause=first.reason,
                    ),
                    now=now,
                )
            )
        return raised


def _raise_for(
    detector: DetectorDeclaration,
    correlation_key: str,
    findings: Sequence[Observation],
) -> IncidentRaise:
    """Return the raise these findings describe.

    The title is the detector's name and the summary counts the subjects, which
    is what makes one incident about fifty resources readable in a list. The
    per-resource detail stays on the subject, where an operator opening the
    incident finds it.
    """
    flapping = any(entry.verdict is Verdict.FLAPPING for entry in findings)
    subjects = tuple(
        IncidentSubject(
            resource_id=entry.resource_id,
            detail=entry.detail,
            evidence=dict(entry.evidence),
            observed_at=entry.observed_at,
        )
        for entry in sorted(findings, key=lambda entry: entry.resource_id)
    )
    lead = findings[0].detail
    summary = f"{len(subjects)} subject(s): {lead}" if len(subjects) > 1 else lead

    return IncidentRaise(
        correlation_key=correlation_key,
        title=f"{detector.name} is flapping" if flapping else detector.name,
        summary=summary,
        origin=IncidentOrigin.DETECTOR,
        origin_id=detector.detector_id,
        severity=detector.severity.value,
        subjects=subjects,
        team_node_id=detector.team_node_id,
        cause=detector.description,
    )


__all__ = ["DETECTOR_FAILURE_SEVERITY", "DetectionIntake", "IntakeReport"]
