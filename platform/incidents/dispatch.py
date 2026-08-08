"""Turning an incident into an investigation, and refusing to start a hundred.

Three things stand between an incident and a run, and each of them handles a
different way the deployment could start more work than anybody wanted.

**Correlation** handles most of it, before this module sees anything: a node
taking twenty guests with it is one incident, so it is one candidate for
dispatch rather than twenty.

**One run per correlation** handles the rest of the ordinary case. An incident
already under investigation does not start a second run when the same condition
fires again, because the second run would investigate the same thing and report
it twice.

**The rate limits** handle the case correlation cannot see: fifty unrelated
things going wrong at once, which is what a power event looks like. Per team,
because a team is the unit an operator budgets attention in, and globally,
because fifty teams each under their own limit is still an unbounded deployment.
They exist from the first commit rather than after the first storm.

The objective is derived rather than written. An incident already knows what is
wrong, which resources it is about, and what evidence led there; asking an
operator to also type an objective would be asking them to restate it, and a run
started from a restatement investigates the restatement.

**Every refusal is recorded.** A dispatch that was held is a fact an operator
needs — "no investigation ran because your team had already started twenty this
hour" is an answer, and an incident sitting at open with no explanation is not.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable

from config.constants.observation import (
    MAX_DISPATCHES_PER_HOUR,
    MAX_DISPATCHES_PER_TEAM_PER_HOUR,
    MAX_INCIDENT_SUBJECTS,
)
from platform.incidents.lifecycle import IncidentLifecycle
from platform.observability.logging import get_logger
from platform.persistence.ports.incident_store import Incident

logger = get_logger(__name__)

#: The window both limits are declared over. An hour, because that is the unit
#: an operator thinks in — "twenty investigations an hour" is a sentence and
#: "one every three minutes" is the same bound stated less usefully.
DISPATCH_WINDOW_SECONDS = 3_600.0


def _utc_now() -> datetime:
    """Return the current instant, timezone-aware."""
    return datetime.now(UTC)


#: Subjects named in an objective before it says "and N others". A prompt that
#: listed five hundred identifiers would spend its context on a list the model
#: cannot act on, and the incident carries all of them for anything that can.
MAX_NAMED_SUBJECTS = 8


def objective_for(incident: Incident) -> str:
    """Return the objective an investigation of ``incident`` is started with.

    Derived from the incident and its subjects, in the order an investigator
    needs them: what is wrong, what it is about, and what was seen. The
    identifiers are named rather than counted because they are what the first
    capability call will use.
    """
    named = incident.subject_ids[:MAX_NAMED_SUBJECTS]
    remaining = len(incident.subject_ids) - len(named)
    subjects = ", ".join(named)
    if remaining > 0:
        subjects = f"{subjects} and {remaining} other(s)"

    evidence = _leading_evidence(incident)
    parts = [
        f"{incident.title}: {incident.summary}".strip(": "),
        f"Affected: {subjects}." if subjects else "",
        f"Observed: {evidence}." if evidence else "",
        "Find the cause and say what evidence supports it.",
    ]
    return " ".join(part for part in parts if part)


def _leading_evidence(incident: Incident, limit: int = MAX_NAMED_SUBJECTS) -> str:
    """Return the first few observations, as ``name=value`` pairs.

    The first few rather than all of them, for the reason the subject list is
    truncated: an objective is a prompt, and a prompt made mostly of numbers is
    one the model reads past.
    """
    pairs: list[str] = []
    for subject in incident.subjects[:MAX_INCIDENT_SUBJECTS]:
        for name, value in subject.evidence.items():
            if name == "observed_at":
                continue
            pairs.append(f"{subject.resource_id} {name}={value}")
            if len(pairs) >= limit:
                return "; ".join(pairs)
    return "; ".join(pairs)


@dataclass(frozen=True, slots=True)
class DispatchDecision:
    """Whether an incident may start an investigation, and why not if it may not."""

    incident_id: str
    allowed: bool
    #: Empty when allowed. Otherwise the sentence an operator reads on the
    #: incident's timeline, naming which of the three gates held it.
    reason: str = ""
    run_id: str = ""

    @property
    def held(self) -> bool:
        """Return whether this dispatch was refused."""
        return not self.allowed


@runtime_checkable
class RunStarter(Protocol):
    """Whatever actually starts an investigation.

    A protocol rather than an import: starting a run is a composition-root
    concern — it needs a provider, a pipeline, and a background task — and this
    module's job is to decide *whether*, not to know how.
    """

    async def start(self, *, incident: Incident, objective: str) -> str:
        """Start an investigation of ``incident`` and return its run identifier."""


@dataclass(slots=True)
class DispatchLimits:
    """A sliding hour of dispatch times, per team and across the deployment.

    Two windows rather than one, and both are needed. A per-team limit alone
    lets fifty teams start a thousand runs; a global limit alone lets one noisy
    team spend everybody else's budget.
    """

    per_team: int = MAX_DISPATCHES_PER_TEAM_PER_HOUR
    overall: int = MAX_DISPATCHES_PER_HOUR
    window_seconds: float = DISPATCH_WINDOW_SECONDS
    clock: Callable[[], datetime] = _utc_now
    started: dict[str, list[datetime]] = field(default_factory=dict)
    #: How many dispatches each team has had held. Counted rather than logged,
    #: because "we are constantly at the limit" is a capacity fact somebody
    #: should be able to read off a screen.
    held: dict[str, int] = field(default_factory=dict)

    def check(self, team_node_id: str, *, at: datetime | None = None) -> str:
        """Return why a dispatch is refused, or the empty string if it is not."""
        moment = at if at is not None else self.clock()
        self._expire(moment)

        team = team_node_id or "unassigned"
        if len(self.started.get(team, ())) >= self.per_team:
            return (
                f"{team} has started {self.per_team} investigations in the last hour, which "
                f"is its limit; this incident is waiting rather than adding to them"
            )
        if sum(len(times) for times in self.started.values()) >= self.overall:
            return (
                f"the deployment has started {self.overall} investigations in the last hour, "
                f"which is its limit; this incident is waiting rather than adding to them"
            )
        return ""

    def record(self, team_node_id: str, *, at: datetime | None = None) -> None:
        """Record that ``team_node_id`` started an investigation."""
        moment = at if at is not None else self.clock()
        self.started.setdefault(team_node_id or "unassigned", []).append(moment)

    def record_held(self, team_node_id: str) -> None:
        """Record that a dispatch for ``team_node_id`` was refused."""
        team = team_node_id or "unassigned"
        self.held[team] = self.held.get(team, 0) + 1

    def _expire(self, now: datetime) -> None:
        """Drop the dispatches that have fallen out of the window."""
        cutoff = now - timedelta(seconds=self.window_seconds)
        for team, times in list(self.started.items()):
            kept = [moment for moment in times if moment > cutoff]
            if kept:
                self.started[team] = kept
            else:
                del self.started[team]


@dataclass(slots=True)
class IncidentDispatcher:
    """The three gates between an incident and an investigation."""

    lifecycle: IncidentLifecycle
    starter: RunStarter
    limits: DispatchLimits = field(default_factory=DispatchLimits)

    async def dispatch(self, incident: Incident, *, now: datetime) -> DispatchDecision:
        """Start an investigation of ``incident``, or say why one did not start."""
        if incident.is_closed:
            return DispatchDecision(
                incident_id=incident.incident_id,
                allowed=False,
                reason=f"the incident is {incident.state.value} and needs no investigation",
            )
        if incident.run_ids:
            # One run per correlation. A second firing of the same condition
            # must not start a second investigation of the same thing: it would
            # reach the same conclusion and report it twice.
            return DispatchDecision(
                incident_id=incident.incident_id,
                allowed=False,
                reason="an investigation is already attached to this incident",
                run_id=incident.run_ids[0],
            )

        refusal = self.limits.check(incident.team_node_id, at=now)
        if refusal:
            self.limits.record_held(incident.team_node_id)
            await self.lifecycle.record_action(
                incident.incident_id, f"dispatch held: {refusal}", now=now
            )
            logger.info(
                "incidents.dispatch_held",
                incident_id=incident.incident_id,
                team=incident.team_node_id,
                reason=refusal,
            )
            return DispatchDecision(incident_id=incident.incident_id, allowed=False, reason=refusal)

        objective = objective_for(incident)
        run_id = await self.starter.start(incident=incident, objective=objective)
        self.limits.record(incident.team_node_id, at=now)
        await self.lifecycle.attach_run(incident.incident_id, run_id, objective=objective, now=now)
        return DispatchDecision(incident_id=incident.incident_id, allowed=True, run_id=run_id)

    async def dispatch_all(
        self, incidents: tuple[Incident, ...], *, now: datetime
    ) -> tuple[DispatchDecision, ...]:
        """Dispatch each incident in turn, most severe first.

        Ordered rather than arbitrary, because the limits mean not everything
        gets a run and the ones that do should be the ones that matter. Sorted
        by severity and then by age, so a critical incident opened five minutes
        ago outranks a low one opened yesterday.
        """
        ordered = sorted(incidents, key=_urgency)
        return tuple([await self.dispatch(incident, now=now) for incident in ordered])


#: Severity, most urgent first, for ordering dispatch. Declared here rather than
#: read off ``Severity.rank`` because an incident carries its severity as the
#: string a webhook sent, and an upstream is free to send one we do not model.
_SEVERITY_ORDER = ("critical", "high", "medium", "low", "noise")


def _urgency(incident: Incident) -> tuple[int, datetime]:
    """Return the sort key that puts the most urgent incident first."""
    try:
        rank = _SEVERITY_ORDER.index(incident.severity)
    except ValueError:
        # An unmodelled severity sorts below the ones we know rather than above
        # them: an upstream's private word is not evidence that it is urgent.
        rank = len(_SEVERITY_ORDER)
    return (rank, incident.opened_at)


__all__ = [
    "DISPATCH_WINDOW_SECONDS",
    "MAX_NAMED_SUBJECTS",
    "DispatchDecision",
    "DispatchLimits",
    "IncidentDispatcher",
    "RunStarter",
    "objective_for",
]
