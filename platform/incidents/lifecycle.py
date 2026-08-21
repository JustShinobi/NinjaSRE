"""The one lifecycle every incident goes through, whatever raised it.

This module is the only place in the repository that constructs an ``Incident``,
and ``tests/architecture`` asserts that structurally. That is not tidiness — it
is the whole of the plan's "one incident lifecycle, whatever raised it". The
alternative shape, an ``Alert`` from webhooks and an ``Incident`` from
detectors, means every downstream component handles two cases and the second one
is the one nobody tests.

So a webhook alert, a detected condition, a failing detector, and a person
opening one by hand all arrive at ``raise_incident``. They differ in the
``origin`` field and in nothing else.

**Raising is idempotent by correlation.** If a live incident already exists for
the cause, the second firing lands on it: new subjects are added, the timeline
records that it correlated, and no second incident appears. Combined with the
derived identifier, two replicas that both concluded the same thing at the same
tick write the same row rather than two.

**Every transition names its cause and its actor.** ``transition`` refuses an
empty cause, because "it closed" is not an answer and a timeline made of
unexplained state changes is a timeline nobody uses to reconstruct an outage.

**A human close needs a reason and works from any state.** FR-018 is
unconditional, and the reason is required for the same purpose the cause is: an
incident closed by somebody who thought it was noise and an incident closed
because it was fixed are different facts.

**Nothing here starts an investigation.** Dispatch is its own module with its
own rate limits, and a lifecycle that started runs would be a lifecycle that
could start a hundred of them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime

from config.constants.observation import MAX_INCIDENT_SUBJECTS
from platform.incidents.errors import IncidentClosed, UnknownIncident
from platform.observability.logging import get_logger
from platform.persistence.ports.incident_store import (
    SYSTEM_ACTOR,
    Incident,
    IncidentOrigin,
    IncidentState,
    IncidentStore,
    IncidentSubject,
    TimelineEntry,
    TimelineKind,
    incident_key,
    timeline_key,
)

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class IncidentRaise:
    """Everything needed to raise an incident, from any origin.

    One record rather than eleven keyword arguments, because three callers build
    it — the tick, the webhook router, and a person through the API — and a
    signature they each spell out is a signature that drifts three ways.
    """

    correlation_key: str
    title: str
    summary: str
    origin: IncidentOrigin
    origin_id: str
    severity: str
    subjects: tuple[IncidentSubject, ...]
    team_node_id: str = ""
    actor: str = SYSTEM_ACTOR
    #: Why this was raised, in the operator's terms. Goes on the opening
    #: timeline entry, so an incident's first line says what happened.
    cause: str = ""
    labels: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class IncidentLifecycle:
    """Raising, correlating, transitioning, and closing — for every origin."""

    store: IncidentStore

    async def raise_incident(self, request: IncidentRaise, *, now: datetime) -> Incident:
        """Return the incident this cause belongs to, opening one if there is none.

        Idempotent twice over. If a live incident exists for the correlation
        key, this correlates onto it; if it does not, the new incident's
        identifier is derived from the key and the instant, so two replicas that
        both raised at the same tick write one row.
        """
        existing = await self.store.open_for(request.correlation_key)
        if existing is not None:
            return await self._correlate(existing, request, now=now)

        incident = Incident(
            incident_id=incident_key(request.correlation_key, now),
            correlation_key=request.correlation_key,
            title=request.title,
            summary=request.summary,
            origin=request.origin,
            origin_id=request.origin_id,
            severity=request.severity,
            state=IncidentState.OPEN,
            opened_at=now,
            subjects=request.subjects[:MAX_INCIDENT_SUBJECTS],
            team_node_id=request.team_node_id,
        )
        stored = await self.store.upsert(incident)
        await self._record(
            stored,
            TimelineKind.OPENED,
            at=now,
            actor=request.actor,
            cause=request.cause or request.summary,
            detail=f"{len(stored.subjects)} subject(s)",
        )
        logger.info(
            "incidents.opened",
            incident_id=stored.incident_id,
            origin=stored.origin.value,
            origin_id=stored.origin_id,
            subjects=len(stored.subjects),
        )
        return stored

    async def transition(
        self,
        incident_id: str,
        to: IncidentState,
        *,
        cause: str,
        actor: str = SYSTEM_ACTOR,
        now: datetime,
    ) -> Incident:
        """Move ``incident_id`` to ``to`` and record why, and who.

        Refuses an empty cause and refuses to move a closed incident. The first
        because a timeline of unexplained state changes reconstructs nothing;
        the second because reopening is a new incident — the condition recurred,
        and writing that into last week's history would lose when it recurred.
        """
        if not cause:
            raise ValueError(
                "A state change needs a cause. 'It closed' is not an answer to the "
                "question an incident timeline exists to answer."
            )
        incident = await self._require(incident_id)
        if incident.is_closed:
            raise IncidentClosed(incident_id, state=incident.state.value)

        moved = replace(
            incident,
            state=to,
            closed_at=now if to.is_closed else incident.closed_at,
        )
        stored = await self.store.upsert(moved)
        await self._record(
            stored,
            TimelineKind.CLOSED if to.is_closed else TimelineKind.STATE_CHANGED,
            at=now,
            actor=actor,
            cause=cause,
            detail=f"{incident.state.value} → {to.value}",
        )
        return stored

    async def attach_run(
        self,
        incident_id: str,
        run_id: str,
        *,
        objective: str = "",
        now: datetime,
    ) -> Incident:
        """Link an investigation to ``incident_id`` and move it to investigating.

        Idempotent in the run: attaching the same run twice is one link, because
        a retried dispatch must not make an incident look like two
        investigations.
        """
        incident = await self._require(incident_id)
        if run_id in incident.run_ids:
            return incident

        linked = replace(
            incident,
            run_ids=(*incident.run_ids, run_id),
            state=IncidentState.INVESTIGATING if incident.state.is_live else incident.state,
        )
        stored = await self.store.upsert(linked)
        await self._record(
            stored,
            TimelineKind.RUN_STARTED,
            at=now,
            actor=SYSTEM_ACTOR,
            cause=objective or "an investigation was started for this incident",
            detail=run_id,
        )
        return stored

    async def record_action(
        self,
        incident_id: str,
        action: str,
        *,
        actor: str = SYSTEM_ACTOR,
        now: datetime,
    ) -> Incident:
        """Record that something was done about ``incident_id``."""
        incident = await self._require(incident_id)
        stored = await self.store.upsert(replace(incident, actions=(*incident.actions, action)))
        await self._record(stored, TimelineKind.ACTION_TAKEN, at=now, actor=actor, cause=action)
        return stored

    async def mark_subject_absent(
        self,
        incident_id: str,
        resource_id: str,
        *,
        now: datetime,
    ) -> Incident:
        """Record that a subject stopped existing while this incident was open.

        The incident is *not* closed by it, and the behaviour is declared here
        rather than emerging from whatever the estate does. A guest that vanished
        mid-incident is a fact about the incident — quite possibly the most
        important one — and an incident that closed itself because its subject
        disappeared would be a deployment losing the evidence that something
        disappeared.
        """
        incident = await self._require(incident_id)
        if resource_id not in incident.subject_ids:
            return incident

        stored = await self.store.upsert(
            replace(
                incident,
                subjects=tuple(
                    replace(subject, absent_since=subject.absent_since or now)
                    if subject.resource_id == resource_id
                    else subject
                    for subject in incident.subjects
                ),
            )
        )
        await self._record(
            stored,
            TimelineKind.SUBJECT_ABSENT,
            at=now,
            actor=SYSTEM_ACTOR,
            cause=f"{resource_id} is no longer in the estate",
            detail="the incident stays open: a subject that vanished is not a resolution",
        )
        return stored

    async def self_close(
        self,
        incident_id: str,
        *,
        cause: str,
        now: datetime,
    ) -> Incident:
        """Close ``incident_id`` because the condition cleared, and say so."""
        incident = await self._require(incident_id)
        if incident.is_closed:
            return incident

        stored = await self.store.upsert(
            replace(
                incident,
                state=IncidentState.RESOLVED,
                closed_at=now,
                close_reason=cause,
                self_resolved=True,
            )
        )
        await self._record(
            stored,
            TimelineKind.CLOSED,
            at=now,
            actor=SYSTEM_ACTOR,
            cause=cause,
            detail="self-resolved",
        )
        logger.info("incidents.self_resolved", incident_id=incident_id, cause=cause)
        return stored

    async def close(
        self,
        incident_id: str,
        *,
        reason: str,
        actor: str,
        state: IncidentState = IncidentState.CLOSED_WITHOUT_ACTION,
        now: datetime,
    ) -> Incident:
        """Close ``incident_id`` because a person said so, at any state.

        The reason is required. An incident closed by somebody who thought it
        was noise and one closed because it was fixed are different facts, and a
        deployment that recorded both as "closed" would have no way to find the
        first kind again.
        """
        if not reason:
            raise ValueError(
                "Closing an incident needs a reason. 'Closed by Ada' does not say "
                "whether it was fixed or dismissed, and those are different facts."
            )
        if not state.is_closed:
            raise ValueError(f"{state.value} is not a terminal state; closing needs one that is.")

        incident = await self._require(incident_id)
        if incident.is_closed:
            return incident

        stored = await self.store.upsert(
            replace(incident, state=state, closed_at=now, close_reason=reason)
        )
        await self._record(
            stored, TimelineKind.CLOSED, at=now, actor=actor, cause=reason, detail=state.value
        )
        return stored

    async def suppress(
        self,
        incident_id: str,
        *,
        by: str,
        reason: str,
        actor: str = SYSTEM_ACTOR,
        now: datetime,
    ) -> Incident:
        """Close ``incident_id`` as suppressed, naming what covered it.

        Recorded rather than silent. An operator asking "why did nothing happen"
        gets an answer, and a suppression rule that is too broad is countable
        instead of invisible.
        """
        incident = await self._require(incident_id)
        if incident.is_closed:
            return incident

        stored = await self.store.upsert(
            replace(
                incident,
                state=IncidentState.SUPPRESSED,
                closed_at=now,
                close_reason=reason,
                suppressed_by=by,
            )
        )
        await self._record(
            stored, TimelineKind.SUPPRESSED, at=now, actor=actor, cause=reason, detail=by
        )
        return stored

    async def timeline(self, incident_id: str) -> tuple[TimelineEntry, ...]:
        """Return ``incident_id``'s history, oldest first."""
        return await self.store.timeline(incident_id)

    # --- reasoning -------------------------------------------------------------

    async def record_alert_received(
        self,
        incident_id: str,
        *,
        labels: Mapping[str, str],
        credential_name: str,
        actor: str = SYSTEM_ACTOR,
        now: datetime,
    ) -> TimelineEntry:
        """Record what the investigation took in: the alert's labels and the
        identity of the delivery that authenticated it.

        ``credential_name`` is the delivery credential's *display* name —
        "delivery token am-cluster", never the secret that authenticated the
        request. There is no parameter here a caller could put the value in:
        the signature is the guarantee, not a convention somebody has to
        remember to follow.
        """
        if not credential_name:
            raise ValueError(
                "Recording an alert's receipt needs the display name of the "
                "credential that authenticated the delivery."
            )
        incident = await self._require(incident_id)
        rendered = ", ".join(f"{key}={value}" for key, value in labels.items())
        return await self._record(
            incident,
            TimelineKind.ALERT_RECEIVED,
            at=now,
            actor=actor,
            cause=f"the delivery was authenticated by {credential_name}",
            detail=rendered,
        )

    async def record_hypotheses(
        self,
        incident_id: str,
        *,
        hypotheses: Sequence[str],
        actor: str = SYSTEM_ACTOR,
        now: datetime,
    ) -> TimelineEntry:
        """Record what the investigation considered before it queried anything.

        Refuses an empty list. An investigation that named nothing has
        nothing here to record, and a hollow entry would read as a step that
        happened when it did not.
        """
        if not hypotheses:
            raise ValueError("Recording hypotheses needs at least one to record.")
        incident = await self._require(incident_id)
        return await self._record(
            incident,
            TimelineKind.HYPOTHESES_DRAWN,
            at=now,
            actor=actor,
            cause="; ".join(hypotheses),
            detail=f"{len(hypotheses)} hypothesis(es)",
        )

    async def record_evidence(
        self,
        incident_id: str,
        *,
        query: str,
        result: str,
        conclusion: str,
        actor: str = SYSTEM_ACTOR,
        now: datetime,
    ) -> TimelineEntry:
        """Record one piece of evidence: what was asked, what came back, and
        what it means.

        ``query`` and ``result`` land on the entry itself, not folded into a
        sentence about them, so a screen can show the block a person can
        check against the query that actually ran instead of trusting a
        summary of it.
        """
        if not query:
            raise ValueError("Recording evidence needs the query that was actually run.")
        incident = await self._require(incident_id)
        return await self._record(
            incident,
            TimelineKind.EVIDENCE,
            at=now,
            actor=actor,
            cause=conclusion,
            query=query,
            result=result,
        )

    async def record_diagnosis(
        self,
        incident_id: str,
        *,
        sentence: str,
        supporting_evidence_ids: Sequence[str] = (),
        actor: str = SYSTEM_ACTOR,
        now: datetime,
    ) -> TimelineEntry:
        """Record the investigation's conclusion — or its best hypothesis.

        Recorded as a diagnosis only when ``supporting_evidence_ids`` names at
        least one evidence entry it rests on. With nothing to point at,
        ``sentence`` is exactly as true or false as it was going to be, but it
        has not been demonstrated: it is recorded as a hypothesis, on the same
        kind the earlier ``record_hypotheses`` entry uses, and it is never
        presented as a diagnosis.
        """
        if not sentence:
            raise ValueError("Recording a diagnosis needs the sentence it concluded.")
        incident = await self._require(incident_id)
        if supporting_evidence_ids:
            return await self._record(
                incident,
                TimelineKind.DIAGNOSIS,
                at=now,
                actor=actor,
                cause=sentence,
                detail=", ".join(supporting_evidence_ids),
            )
        return await self._record(
            incident,
            TimelineKind.HYPOTHESES_DRAWN,
            at=now,
            actor=actor,
            cause=sentence,
            detail="no evidence supports this yet",
        )

    async def record_report_delivered(
        self,
        incident_id: str,
        *,
        destinations: Sequence[str],
        actor: str = SYSTEM_ACTOR,
        now: datetime,
    ) -> TimelineEntry:
        """Record that the investigation's report went out, and to where."""
        if not destinations:
            raise ValueError("Recording a delivered report needs at least one destination.")
        incident = await self._require(incident_id)
        return await self._record(
            incident,
            TimelineKind.REPORT_DELIVERED,
            at=now,
            actor=actor,
            cause="the investigation's report was delivered",
            detail=", ".join(destinations),
        )

    # --- internals -----------------------------------------------------------

    async def _correlate(
        self, existing: Incident, request: IncidentRaise, *, now: datetime
    ) -> Incident:
        """Land ``request`` on the incident already open for its cause."""
        known = set(existing.subject_ids)
        added = tuple(subject for subject in request.subjects if subject.resource_id not in known)
        merged = tuple(_freshened(subject, request.subjects) for subject in existing.subjects)
        stored = await self.store.upsert(
            replace(existing, subjects=(merged + added)[:MAX_INCIDENT_SUBJECTS])
        )

        await self._record(
            stored,
            TimelineKind.CORRELATED,
            at=now,
            actor=request.actor,
            cause=request.cause or request.summary,
            detail=f"{len(added)} new subject(s), {len(stored.subjects)} in total",
        )
        for subject in added:
            await self._record(
                stored,
                TimelineKind.SUBJECT_ADDED,
                at=now,
                actor=request.actor,
                cause=subject.detail or "the same condition fired on this resource too",
                detail=subject.resource_id,
            )
        return stored

    async def _record(
        self,
        incident: Incident,
        kind: TimelineKind,
        *,
        at: datetime,
        actor: str,
        cause: str,
        detail: str = "",
        query: str = "",
        result: str = "",
    ) -> TimelineEntry:
        """Append one entry to ``incident``'s timeline and return it."""
        entry = TimelineEntry(
            entry_id=timeline_key(f"{incident.incident_id}:{detail}", kind, at),
            incident_id=incident.incident_id,
            kind=kind,
            at=at,
            actor=actor,
            cause=cause,
            detail=detail,
            query=query,
            result=result,
        )
        await self.store.append((entry,))
        return entry

    async def _require(self, incident_id: str) -> Incident:
        """Return the incident, or raise naming the one that is missing."""
        incident = await self.store.get(incident_id)
        if incident is None:
            raise UnknownIncident(incident_id)
        return incident


def _freshened(subject: IncidentSubject, incoming: tuple[IncidentSubject, ...]) -> IncidentSubject:
    """Return ``subject`` with what a re-firing knows about it brought up to date.

    The detail, the evidence, and the instant, and nothing else. A subject that
    fired again with a worse number should show the worse number; its absence
    marker and its place in the list are history and must not be rewritten.
    """
    for candidate in incoming:
        if candidate.resource_id == subject.resource_id:
            return replace(
                subject,
                detail=candidate.detail or subject.detail,
                evidence=dict(candidate.evidence) or dict(subject.evidence),
                observed_at=candidate.observed_at or subject.observed_at,
            )
    return subject


__all__ = ["IncidentLifecycle", "IncidentRaise"]
