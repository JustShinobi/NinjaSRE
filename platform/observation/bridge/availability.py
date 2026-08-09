"""What happens to the detectors when the metrics system they read stops answering.

The worst failure mode any monitoring system has is looking healthy because it
stopped looking, and a bridge is the easiest place in this deployment to build
one: point a detector at Prometheus, let Prometheus fall over, and every
threshold detector reads an empty window and concludes there is nothing wrong.

Two things happen instead, and neither is optional.

**The outage is itself an incident.** Somebody has to be told that the thing
that would have told them has gone. On the reference cluster this is not
hypothetical — the whole observability stack runs as containers on one node, and
during that cluster's only total outage not a single alert fired.

**Every detector that read the source reports that it could not be evaluated.**
Not "clear", not "insufficient data", and not skipped. ``DetectorFailure`` is
already the shape observation uses for a detector that threw, and its summary
already says the sentence that matters — until it can be evaluated, nothing is
watching for what it watches for.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from platform.incidents.lifecycle import IncidentRaise
from platform.notifications.models import Severity
from platform.observation.detectors.model import DetectorDeclaration
from platform.observation.evaluation import DetectorFailure
from platform.persistence.ports.incident_store import IncidentOrigin, IncidentSubject

#: What an outage's correlation key is prefixed with. Its own namespace, because
#: "Prometheus is down" and "the datastore is full" must never correlate onto
#: each other however many detectors they share.
OUTAGE_PREFIX = "bridge"

#: What the incident about an unreachable source calls its subject. The source
#: rather than a resource: the estate is not what is wrong, and naming a guest
#: would send an investigation to look at the wrong thing.
OUTAGE_SUBJECT_PREFIX = "source"


@dataclass(frozen=True, slots=True)
class SourceOutage:
    """A source that did not answer, and what depended on it."""

    source: str
    reason: str
    at: datetime
    #: The signals this source was the one producing. Carried so that "which
    #: detectors are blind now" is answerable from the outage rather than by
    #: re-deriving the wiring at the moment it has stopped working.
    signals: tuple[str, ...] = ()

    @property
    def summary(self) -> str:
        """Return the sentence the incident about this outage carries."""
        watched = ", ".join(self.signals) if self.signals else "no signals"
        return (
            f"the observability source {self.source!r} did not answer: {self.reason}. "
            f"It is what produces {watched}, so the detectors reading them are reporting "
            f"that they cannot be evaluated rather than that nothing is wrong."
        )


def failures_for_outage(
    detectors: Sequence[DetectorDeclaration],
    *,
    outage: SourceOutage,
) -> tuple[DetectorFailure, ...]:
    """Return one failure per detector that read a signal ``outage`` was producing.

    Detectors reading signals the deployment gathers itself are untouched, which
    is the whole reason precedence is per signal: a Prometheus running inside the
    estate it monitors takes its own signals with it and must not take the rest.
    """
    affected = set(outage.signals)
    return tuple(
        DetectorFailure(
            detector_id=detector.detector_id,
            reason=(f"its source {outage.source!r} did not answer: {outage.reason}"),
            failed_at=outage.at,
        )
        for detector in detectors
        if detector.signal in affected
    )


def raise_for_outage(outage: SourceOutage, *, team_node_id: str = "") -> IncidentRaise:
    """Return the incident this outage opens, in the same shape a detected one takes.

    ``DETECTOR`` rather than a fourth origin. The deployment noticed this itself,
    which is what that origin means; adding an origin for "the bridge noticed"
    would be a second kind of incident for a fact that is the same kind.
    """
    return IncidentRaise(
        correlation_key=f"{OUTAGE_PREFIX}:{outage.source}",
        title=f"the metrics source {outage.source} is not answering",
        summary=outage.summary,
        origin=IncidentOrigin.DETECTOR,
        origin_id=OUTAGE_PREFIX,
        severity=Severity.HIGH.value,
        subjects=(
            IncidentSubject(
                resource_id=f"{OUTAGE_SUBJECT_PREFIX}:{outage.source}",
                detail=outage.reason,
                evidence={
                    "source": outage.source,
                    "signals": ",".join(outage.signals),
                },
                observed_at=outage.at,
            ),
        ),
        team_node_id=team_node_id,
        cause=outage.summary,
    )


def outage_for(
    error: Exception,
    *,
    source: str,
    at: datetime,
    signals: Iterable[str] = (),
) -> SourceOutage:
    """Return the outage ``error`` describes, whatever the transport raised.

    Whatever came back — a refused connection, a timeout, a proxy error — the
    one outcome that must not follow is the deployment continuing as though the
    source had answered.
    """
    reason = getattr(error, "reason", "") or f"{type(error).__name__}: {error}"
    return SourceOutage(source=source, reason=reason, at=at, signals=tuple(signals))


__all__ = [
    "OUTAGE_PREFIX",
    "OUTAGE_SUBJECT_PREFIX",
    "SourceOutage",
    "failures_for_outage",
    "outage_for",
    "raise_for_outage",
]
