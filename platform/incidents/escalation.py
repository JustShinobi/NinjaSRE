"""Following up on an incident nobody addressed, and stopping when somebody does.

A thin bridge over ``platform/notifications/escalation.py`` rather than a second
mechanism. That registry already knows how to schedule a follow-up, cancel it
when the underlying item resolves, bound the number of rounds, and answer "what
is due at this instant" without owning a timer. Re-implementing any of that here
would give the deployment two things that page people and one of them would
eventually keep paging after the other stopped.

What this adds is exactly two facts the registry cannot know.

**An incident is the item.** Its identifier is the registry's key, so cancelling
is a lookup rather than a search — and cancelling on close is unconditional
rather than best-effort.

**Closing cancels.** Every terminal state cancels the follow-up, including
suppressed and closed-without-action. An escalation that fired after somebody
dismissed an incident is exactly the interruption that teaches people to filter
escalations, after which the next real one is filtered too.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from platform.notifications.escalation import Escalation, EscalationRegistry
from platform.notifications.models import NotificationSink, Severity
from platform.observability.logging import get_logger
from platform.persistence.ports.incident_store import (
    SYSTEM_ACTOR,
    Incident,
    IncidentState,
    TimelineEntry,
    TimelineKind,
    timeline_key,
)

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class IncidentEscalation:
    """Scheduling, firing, and cancelling an incident's follow-up."""

    registry: EscalationRegistry
    #: Where an escalation goes when the incident's team declares nothing. The
    #: sink is a notification concern; this module only has to name one.
    default_sink: NotificationSink

    def schedule(self, incident: Incident, *, at: datetime) -> Escalation | None:
        """Schedule a follow-up for ``incident``, or nothing if it is already closed.

        A closed incident is never escalated, including one that closed in the
        same tick it opened — a condition that cleared inside its own recovery
        window should not page anybody about having cleared.
        """
        if incident.is_closed:
            return None
        return self.registry.schedule(
            incident.incident_id,
            subject=incident.title,
            team_node_id=incident.team_node_id,
            sink=self.default_sink,
            severity=_severity(incident.severity),
            run_id=incident.run_ids[0] if incident.run_ids else "",
            summary=incident.summary,
            at=at,
        )

    def cancel(self, incident: Incident, *, reason: str = "") -> Escalation | None:
        """Cancel ``incident``'s follow-up because the incident ended.

        Returns ``None`` when nothing was pending, which is the ordinary case
        rather than an error: most incidents close before their first round.
        """
        cancelled = self.registry.resolve(
            incident.incident_id,
            reason=reason or f"the incident {_ended(incident.state)}",
        )
        if cancelled is not None:
            logger.info(
                "incidents.escalation_cancelled",
                incident_id=incident.incident_id,
                state=incident.state.value,
            )
        return cancelled

    def due(self, *, at: datetime) -> tuple[Escalation, ...]:
        """Return the escalations that fire now, advancing each one."""
        return self.registry.due(at=at)

    def timeline_entries(
        self, escalations: Sequence[Escalation], *, at: datetime
    ) -> tuple[TimelineEntry, ...]:
        """Return the timeline entries these firings leave on their incidents.

        Written to the incident rather than only to a notification log, because
        "nobody was told" and "three people were told and nobody looked" are
        different facts and only the incident's own history distinguishes them.
        """
        return tuple(
            TimelineEntry(
                entry_id=timeline_key(escalation.item_id, TimelineKind.ESCALATED, at),
                incident_id=escalation.item_id,
                kind=TimelineKind.ESCALATED,
                at=at,
                actor=SYSTEM_ACTOR,
                cause=escalation.describe(),
                detail=f"round {escalation.round}",
            )
            for escalation in escalations
        )


def _severity(value: str) -> Severity:
    """Return the escalation severity an incident's own severity implies.

    Unmodelled words become ``HIGH`` rather than raising. An upstream's private
    severity is not a reason to refuse to escalate; it is a reason to escalate
    at the level a human would assume.
    """
    try:
        return Severity(value)
    except ValueError:
        return Severity.HIGH


def _ended(state: IncidentState) -> str:
    """Return how an incident in ``state`` ended, in the operator's terms."""
    match state:
        case IncidentState.RESOLVED:
            return "resolved"
        case IncidentState.SUPPRESSED:
            return "was suppressed"
        case IncidentState.CLOSED_WITHOUT_ACTION:
            return "was closed without action"
        case _:
            return "is no longer waiting"


__all__ = ["IncidentEscalation"]
