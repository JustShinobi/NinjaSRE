"""The noun an investigation result attaches to, and the history of how it got there.

The fifteenth port. Everything above it treats an incident as *the* unit of
something being wrong, whatever noticed — a detector, a webhook, or a person —
and the shapes below are what make that possible rather than aspirational.

**One state set, closed.** Seven members and no ``other``. A provider-shaped
escape hatch would immediately be filled with provider strings, at which point
"how many incidents are open" stops having an answer. A state that maps to
nothing is a caller bug, not a new member.

**An incident carries its subjects, not a count.** One cause across fifty
resources is one incident with fifty subjects, and every one of them is named.
A count would make correlation unfalsifiable: an operator who suspected the
grouping was too broad would have nothing to check it against.

**Evidence is structural.** ``Incident`` refuses to be constructed with no
subject, and a subject carries what was observed. Article I says a conclusion
carries the observations that support it, and an incident is the strongest
conclusion this platform draws — so an incident with no evidence is
unrepresentable rather than merely discouraged.

**The timeline is append-only and every entry names an actor.** "It closed" is
not an answer; "the recovery condition held for five minutes and the deployment
closed it" is. The actor is on every entry because the difference between the
deployment doing something and a person doing it is the difference an operator
is actually asking about.

**Correlation is a lookup, not a scan.** ``open_for`` answers "is there already
an incident for this cause" in one indexed read, which is what makes the second
firing of a condition correlate rather than open a second incident.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Final, Protocol, runtime_checkable

from config.constants.observation import (
    MAX_INCIDENT_PAGE_SIZE,
    MAX_INCIDENT_SUBJECTS,
    MAX_INCIDENT_TIMELINE,
)
from config.constants.persistence import MAX_IDENTIFIER_CHARS
from platform.persistence.errors import BoundExceeded


class IncidentState(StrEnum):
    """Everything an incident may be. There is no eighth member."""

    #: Raised, and nothing has picked it up.
    OPEN = "open"
    #: An investigation is running against it.
    INVESTIGATING = "investigating"
    #: The deployment has asked a person something and is waiting.
    AWAITING_HUMAN = "awaiting_human"
    #: A remediation is being applied.
    REMEDIATING = "remediating"
    #: The condition cleared, or the remediation worked. Terminal.
    RESOLVED = "resolved"
    #: A suppression rule or a maintenance window covered it. Terminal, and
    #: recorded rather than silent: an operator asking "why did nothing happen"
    #: gets an answer, and a rule that is too broad is countable.
    SUPPRESSED = "suppressed"
    #: A person closed it without anything being done. Terminal.
    CLOSED_WITHOUT_ACTION = "closed_without_action"

    @property
    def is_closed(self) -> bool:
        """Return whether this state is terminal."""
        return self in {
            IncidentState.RESOLVED,
            IncidentState.SUPPRESSED,
            IncidentState.CLOSED_WITHOUT_ACTION,
        }

    @property
    def is_live(self) -> bool:
        """Return whether this incident is still somebody's problem."""
        return not self.is_closed


class IncidentOrigin(StrEnum):
    """What raised this incident.

    Recorded so an operator can tell where an incident came from, and
    deliberately *not* a second lifecycle. A webhook alert and a detected
    condition differ in this field and in nothing else.
    """

    DETECTOR = "detector"
    ALERT = "alert"
    HUMAN = "human"


class TimelineKind(StrEnum):
    """What one entry on an incident's timeline records.

    Ten lifecycle members and five reasoning ones, on one enum rather than
    two. A second, parallel "investigation steps" list would be a second
    source of truth for the same incident's history — the timeline is append
    to one sequence, in the order things actually happened, whatever kind
    each entry is.
    """

    OPENED = "opened"
    #: A second firing of the same cause landed on this incident.
    CORRELATED = "correlated"
    SUBJECT_ADDED = "subject_added"
    #: A subject stopped existing while this incident was open.
    SUBJECT_ABSENT = "subject_absent"
    STATE_CHANGED = "state_changed"
    RUN_STARTED = "run_started"
    #: The investigation took in what started it: the labels it arrived
    #: with and the identity of the delivery that authenticated it.
    ALERT_RECEIVED = "alert_received"
    #: The hypotheses the investigation considered, named before any
    #: integration was queried.
    HYPOTHESES_DRAWN = "hypotheses_drawn"
    #: One piece of evidence. Carries the query actually run and the result
    #: it returned on the entry itself — see ``TimelineEntry.query`` and
    #: ``TimelineEntry.result`` — not only a sentence about them.
    EVIDENCE = "evidence"
    #: The investigation's conclusion, as one sentence, referencing the
    #: evidence entries that support it. A conclusion with nothing to point
    #: at is a hypothesis, not a diagnosis, and is recorded as one.
    DIAGNOSIS = "diagnosis"
    #: The report went out. Names the destinations it went to.
    REPORT_DELIVERED = "report_delivered"
    ACTION_TAKEN = "action_taken"
    ESCALATED = "escalated"
    SUPPRESSED = "suppressed"
    CLOSED = "closed"


#: The actor an entry names when the deployment itself did something. A constant
#: rather than an empty string, because "nobody" and "the system" read very
#: differently on a timeline somebody is using to reconstruct an outage.
SYSTEM_ACTOR = "system:observation"


@dataclass(frozen=True, slots=True)
class IncidentSubject:
    """One resource this incident is about, and what was seen on it."""

    resource_id: str
    #: What the detector or the alert said about *this* resource, in one phrase.
    detail: str = ""
    #: The values the conclusion was reached from. Strings for the reason
    #: ``HealthSignal.value`` is: half of what a provider reports is a word.
    evidence: Mapping[str, str] = field(default_factory=dict)
    observed_at: datetime | None = None
    #: Set when the resource went away while this incident was open. The
    #: incident is not closed by it — a guest that vanished mid-incident is a
    #: fact about the incident, not a resolution of it.
    absent_since: datetime | None = None


@dataclass(frozen=True, slots=True)
class TimelineEntry:
    """One thing that happened to an incident, with its cause and its actor."""

    entry_id: str
    incident_id: str
    kind: TimelineKind
    at: datetime
    #: Who or what did it. ``SYSTEM_ACTOR`` for the deployment's own decisions.
    actor: str = SYSTEM_ACTOR
    #: Why. Never empty for a state change: "it closed" is not an answer.
    cause: str = ""
    detail: str = ""
    #: The query an evidence entry actually ran. Empty on every kind but
    #: ``EVIDENCE`` — the text of the query, not a sentence describing it, so
    #: a screen can render what was actually asked.
    query: str = ""
    #: What ``query`` returned. Carried beside it rather than folded into
    #: ``cause`` or ``detail``, because a conclusion that cannot point at the
    #: result it rests on is a hypothesis, not a diagnosis (Article I).
    result: str = ""


@dataclass(frozen=True, slots=True)
class Incident:
    """One thing that is wrong, whatever noticed it.

    Refuses to be constructed without a subject and without a correlation key.
    The first is Article I — an incident is a conclusion and a conclusion
    carries its evidence. The second is what makes the second firing of a cause
    correlate rather than opening a second incident, and an incident that could
    not be looked up by cause would silently defeat that.
    """

    incident_id: str
    correlation_key: str
    title: str
    summary: str
    origin: IncidentOrigin
    #: The detector, the alert source, or the person. Never empty.
    origin_id: str
    severity: str
    state: IncidentState
    opened_at: datetime
    subjects: tuple[IncidentSubject, ...]
    closed_at: datetime | None = None
    team_node_id: str = ""
    #: The investigations attached to this incident, oldest first.
    run_ids: tuple[str, ...] = ()
    #: What was actually done, in the order it was done.
    actions: tuple[str, ...] = ()
    #: Why it closed. Required of a human close, and filled in by the deployment
    #: for a self-resolution so the two read the same way on a screen.
    close_reason: str = ""
    #: Whether the condition cleared on its own rather than anybody acting.
    self_resolved: bool = False
    #: The suppression rule or maintenance window that covered it, if any.
    suppressed_by: str = ""

    def __post_init__(self) -> None:
        if not self.correlation_key:
            raise ValueError(
                "An incident needs a correlation key. Without one the second firing of "
                "the same cause opens a second incident, which is the failure "
                "correlation exists to prevent."
            )
        if not self.origin_id:
            raise ValueError(
                "An incident needs to name what raised it: a detector, an alert source, "
                "or a person."
            )
        if not self.subjects:
            raise ValueError(
                "An incident needs at least one subject. A conclusion carries the "
                "observations that support it, and an incident with nothing to point "
                "at is an assertion."
            )
        if len(self.subjects) > MAX_INCIDENT_SUBJECTS:
            raise BoundExceeded(
                parameter="incident subjects",
                requested=len(self.subjects),
                limit=MAX_INCIDENT_SUBJECTS,
                constant="MAX_INCIDENT_SUBJECTS",
            )

    @property
    def is_closed(self) -> bool:
        """Return whether this incident is terminal."""
        return self.state.is_closed

    @property
    def subject_ids(self) -> tuple[str, ...]:
        """Return the resources this incident is about, in order."""
        return tuple(subject.resource_id for subject in self.subjects)


@dataclass(frozen=True, slots=True)
class IncidentQuery:
    """Every dimension an incident listing can be sliced by.

    Empty tuples mean "no filter on this dimension" rather than "match nothing",
    for the reason ``EstateQuery`` gives: it is the only reading that composes
    when a caller builds a query out of optional inputs.
    """

    states: tuple[IncidentState, ...] = ()
    origins: tuple[IncidentOrigin, ...] = ()
    severities: tuple[str, ...] = ()
    detector_ids: tuple[str, ...] = ()
    subject_id: str = ""
    team_node_id: str | None = None
    opened_after: datetime | None = None
    #: Closed incidents are included by default, because "what happened last
    #: night" is the question an incident list is most often opened to answer.
    live_only: bool = False
    limit: int = 50


#: How much of a digest stands in for the part of a key that did not fit.
#: Sixteen hex characters is sixty-four bits: enough that two keys colliding is
#: not a thing that happens, short enough to leave the readable part readable.
_KEY_DIGEST_CHARS: Final = 16


def _bounded(variable: str, suffix: str) -> str:
    """Return ``variable + suffix``, shortened to fit an identifier column.

    The suffix is kept whole — it is the part an operator reading a key
    recognises, and it is bounded by construction. The variable part is the one
    that grows, so it is what gets truncated, with a digest of the *whole*
    composition appended so two keys that differed before still differ after.

    Deterministic, which is the property every caller here depends on: a retried
    write has to land on the row the first attempt made.
    """
    composed = f"{variable}{suffix}"
    if len(composed) <= MAX_IDENTIFIER_CHARS:
        return composed
    digest = hashlib.sha256(composed.encode()).hexdigest()[:_KEY_DIGEST_CHARS]
    marked = f"{suffix}#{digest}"
    return f"{variable[: MAX_IDENTIFIER_CHARS - len(marked)]}{marked}"


def incident_key(correlation_key: str, opened_at: datetime) -> str:
    """Return the identifier one incident for one cause at one instant gets.

    Deterministic, for the reason the scheduler's fire key is: two replicas that
    both concluded a condition was firing at the same tick derive the same
    identifier, and the second write lands on the first rather than beside it.
    A later recurrence of the same cause opens at a different instant and
    therefore gets its own incident, which is what keeps "it happened again"
    from being written into last week's history.
    """
    return _bounded(correlation_key, f"@{opened_at.isoformat()}")


def timeline_key(incident_id: str, kind: TimelineKind, at: datetime) -> str:
    """Return the identifier one timeline entry gets.

    Derived for the same reason, so a retried transition appends one entry
    rather than two — a timeline that double-records is a timeline an operator
    stops trusting to reconstruct what happened.

    Bounded, because the caller composes ``incident_id`` with free text — a
    resource identifier, "3 subject(s)" — and an incident correlated on a full
    digest and opened at a microsecond instant composes past the width of the
    column this is the key of. That failed on write with a database error that
    read like an outage, and only against a real PostgreSQL: the in-memory store
    every other test uses has no widths.

    The shortening keeps the two properties the key exists for. It is still
    deterministic, so a retry lands on the same row; and it still separates
    entries, because what it digests is the whole of what was composed.
    """
    return _bounded(incident_id, f"@{kind.value}@{at.isoformat()}")


def check_incident_limit(limit: int) -> int:
    """Return ``limit``, or raise if it exceeds the incident page bound."""
    if limit > MAX_INCIDENT_PAGE_SIZE:
        raise BoundExceeded(
            parameter="limit",
            requested=limit,
            limit=MAX_INCIDENT_PAGE_SIZE,
            constant="MAX_INCIDENT_PAGE_SIZE",
        )
    if limit < 1:
        raise ValueError(f"limit must be at least 1, got {limit}.")
    return limit


def check_timeline_limit(limit: int) -> int:
    """Return ``limit``, or raise if it exceeds the timeline bound.

    Its own bound rather than the page one, and larger: a listing is a screen an
    operator pages through, while a timeline is one incident's whole narrative
    and is read in a single go.
    """
    if limit > MAX_INCIDENT_TIMELINE:
        raise BoundExceeded(
            parameter="limit",
            requested=limit,
            limit=MAX_INCIDENT_TIMELINE,
            constant="MAX_INCIDENT_TIMELINE",
        )
    if limit < 1:
        raise ValueError(f"limit must be at least 1, got {limit}.")
    return limit


def matches(incident: Incident, query: IncidentQuery) -> bool:
    """Return whether ``incident`` satisfies every filter ``query`` declares.

    Shared by both backends because it is contract: a listing that meant one
    thing in memory and another in PostgreSQL would make the console and the
    CLI disagree about how many incidents are open.
    """
    if query.live_only and incident.is_closed:
        return False
    if query.states and incident.state not in query.states:
        return False
    if query.origins and incident.origin not in query.origins:
        return False
    if query.severities and incident.severity not in query.severities:
        return False
    if query.detector_ids and incident.origin_id not in query.detector_ids:
        return False
    if query.subject_id and query.subject_id not in incident.subject_ids:
        return False
    if query.team_node_id is not None and incident.team_node_id != query.team_node_id:
        return False
    return not (query.opened_after is not None and incident.opened_at < query.opened_after)


@runtime_checkable
class IncidentStore(Protocol):
    """One organisation's incidents and their timelines, inside one transaction."""

    async def upsert(self, incident: Incident) -> Incident:
        """Store ``incident``, replacing any earlier record with the same id."""

    async def get(self, incident_id: str) -> Incident | None:
        """Return the incident with ``incident_id``, or ``None``."""

    async def open_for(self, correlation_key: str) -> Incident | None:
        """Return the *live* incident for ``correlation_key``, or ``None``.

        Live rather than most-recent, and that is the whole of correlation: a
        second firing of a cause lands on the incident that is still open, and a
        recurrence after a resolution opens a new one rather than reviving a
        piece of last week's history.
        """

    async def query(self, query: IncidentQuery) -> tuple[Incident, ...]:
        """Return the incidents matching ``query``, most recently opened first.

        Raises ``BoundExceeded`` above ``MAX_INCIDENT_PAGE_SIZE``.
        """

    async def append(self, entries: tuple[TimelineEntry, ...]) -> tuple[TimelineEntry, ...]:
        """Append ``entries`` to their incidents' timelines and return them.

        Idempotent by derived identity: a retried transition appends one entry
        rather than two.
        """

    async def timeline(
        self,
        incident_id: str,
        *,
        limit: int = MAX_INCIDENT_TIMELINE,
    ) -> tuple[TimelineEntry, ...]:
        """Return ``incident_id``'s history, oldest first.

        Oldest first, unlike every other history in this package, because a
        timeline is read as a narrative and a narrative told backwards is not
        one.
        """

    async def purge(self, *, before: datetime) -> int:
        """Delete incidents closed before ``before`` and return how many went.

        Only closed ones. An open incident is somebody's current problem
        whatever its age, and a retention sweep that deleted one would be a
        deployment forgetting what it had told an operator about.
        """


__all__ = [
    "SYSTEM_ACTOR",
    "Incident",
    "IncidentOrigin",
    "IncidentQuery",
    "IncidentState",
    "IncidentStore",
    "IncidentSubject",
    "TimelineEntry",
    "TimelineKind",
    "check_incident_limit",
    "check_timeline_limit",
    "incident_key",
    "matches",
    "timeline_key",
]
