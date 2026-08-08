"""Putting every step of the loop on the incident's own timeline, with its cause.

FR-023 asks that proposal, resolution, execution, verification, rollback and
recurrence all appear on the timeline and in the audit log with an actor and a
cause. The audit half is ``ClosedLoopAuditor``; this is the half a human reads.

**The actor is the deployment, never the agent.** An autonomous verification was
performed by the platform on a schedule; attributing it to the agent that
proposed the action would put a principal on it who had gone home. The
``SYSTEM_ACTOR`` the incident package already uses is the one this writes.

**The cause is a sentence, not a code.** "verification: ineffective" sends
somebody to read the code; "clear_cache on store-cove: filesystem.used_percent
96 → 94. The incident is escalated rather than closed." is the thing they were
going to have to reconstruct anyway.

**Resolution closes; everything else escalates.** An effective verification is
the only one that closes an incident, and it closes it with the values, so the
close reason on the record answers "how do you know" without a second lookup. A
recurrence does not touch the incident at all — it is a different noun, it is
raised beside the incident rather than onto it, and folding it in is what would
make "how many incidents are open" stop having an answer.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from platform.incidents.errors import IncidentClosed, UnknownIncident
from platform.incidents.lifecycle import IncidentLifecycle
from platform.observability.logging import get_logger
from platform.persistence.ports.incident_store import IncidentState
from platform.persistence.ports.remediation_ledger import RecurringProblem
from platform.remediation.aftermath import Aftermath
from platform.remediation.models import utc_now

_LOG = get_logger(__name__)

#: What the timeline calls the deployment when it verified something. Distinct
#: from the observation actor, because "the detector concluded" and "the
#: verification concluded" are different claims about different machinery, and
#: an operator reconstructing an outage is reading for exactly that difference.
VERIFICATION_ACTOR = "system:remediation"


@dataclass(slots=True)
class IncidentOutcomes:
    """Writes what a verdict caused onto the incident it was about.

    Every method tolerates an incident that is missing or already closed. A
    verification lands minutes after the action, and in that time a person may
    have closed the incident by hand — which is their prerogative, and a closed
    loop that raised because somebody was faster than it would turn an ordinary
    race into an alert.
    """

    incidents: IncidentLifecycle
    clock: Callable[[], datetime] = field(default=utc_now)

    async def resolved(self, aftermath: Aftermath) -> None:
        """Close the incident with the before-and-after values and the time it took."""
        incident_id = aftermath.outcome.incident_id
        if not incident_id:
            return
        at = self.clock()
        await self._record_action(incident_id, aftermath, at=at)
        await self._transition(
            incident_id,
            IncidentState.RESOLVED,
            cause=aftermath.describe(),
            at=at,
        )

    async def escalated(self, aftermath: Aftermath) -> None:
        """Record what was tried, what was seen, and that a person is needed."""
        incident_id = aftermath.outcome.incident_id
        if not incident_id:
            return
        at = self.clock()
        await self._record_action(incident_id, aftermath, at=at)
        await self._transition(
            incident_id,
            IncidentState.AWAITING_HUMAN,
            cause=aftermath.describe(),
            at=at,
        )

    async def recurrence(self, problem: RecurringProblem) -> None:
        """Note the pattern beside the incidents rather than inside one.

        Deliberately a log line and nothing on any incident's timeline. A
        recurring problem is a different noun — it names a pattern and is closed
        by a change — and writing it onto the fourth incident would file the
        pattern under the last of its symptoms.
        """
        _LOG.warning(
            "remediation.recurring_problem_raised",
            problem_id=problem.problem_id,
            pattern_key=problem.pattern_key,
            occurrences=problem.occurrences,
            incidents=len(problem.incident_ids),
        )

    async def _record_action(self, incident_id: str, aftermath: Aftermath, *, at: datetime) -> None:
        """Add the verification to what was done about this incident."""
        try:
            await self.incidents.record_action(
                incident_id,
                aftermath.describe(),
                actor=VERIFICATION_ACTOR,
                now=at,
            )
        except UnknownIncident:
            _LOG.debug("remediation.timeline_incident_missing", incident_id=incident_id)

    async def _transition(
        self,
        incident_id: str,
        to: IncidentState,
        *,
        cause: str,
        at: datetime,
    ) -> None:
        """Move the incident, tolerating one a person has already closed."""
        try:
            await self.incidents.transition(
                incident_id, to, cause=cause, actor=VERIFICATION_ACTOR, now=at
            )
        except UnknownIncident:
            _LOG.debug("remediation.timeline_incident_missing", incident_id=incident_id)
        except IncidentClosed:
            # Somebody closed it while the settle period ran. Their decision
            # stands; the action and its verdict are already on the timeline
            # through ``record_action``, so nothing is lost by not moving it.
            _LOG.info(
                "remediation.timeline_incident_already_closed",
                incident_id=incident_id,
                intended=to.value,
            )


__all__ = [
    "VERIFICATION_ACTOR",
    "IncidentOutcomes",
]
