"""What each remediation did, whether it worked, and the patterns that emerge.

The sixteenth port, and the first whose rows change state twice: written when an
action executes, claimed when its settle period elapses, and closed when a
verdict is reached. That progression is what makes it one table rather than
three, and the decision is worth the paragraph.

**An obligation and an effectiveness record are the same row.** The thing that
says "read these signals again at 14:05" is the thing that afterwards says "this
capability worked on this resource". Splitting them would mean copying the
before-values from one table to the other at exactly the moment the system is
least sure of itself, and a copy that failed would leave a verdict with nothing
to compare against.

**Claiming is a lease, not a lock.** A worker that dies holding an obligation
blocks it for the lease and no longer, because a verification nobody performs is
an action reported as awaiting verification forever. ``attempts`` counts the
claims rather than the verdicts, so a repeatedly-crashing worker is visible as
what it is instead of as a signal that keeps failing to move.

**Effectiveness aggregates without paging.** ``effectiveness`` returns counts,
not records. It is asked on the path of a proposal, over a year of history, and
a count assembled from the first page would be an answer that got more wrong the
longer the deployment ran. ``history`` is the paged listing, for a human reading
the individual rows.

**A recurring problem is a different noun from an incident.** Four incidents
about one container filling up are one problem and four symptoms; the problem
names the pattern, is looked up by it while it is live, and is closed by a
change rather than by a remediation. It lives here rather than in
``IncidentStore`` because it is derived from this ledger's counts and because an
incident query that returned patterns would make "how many incidents are open"
stop having an answer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from config.constants.closed_loop import (
    MAX_EFFECTIVENESS_PAGE_SIZE,
    MAX_RECURRING_PROBLEM_PAGE_SIZE,
    MAX_VERIFICATION_CLAIM_BATCH,
    VERIFICATION_EFFECTIVE,
    VERIFICATION_INCONCLUSIVE,
    VERIFICATION_INEFFECTIVE,
    VERIFICATION_LEASE_SECONDS,
    VERIFICATION_UNVERIFIABLE,
    VERIFICATION_WORSENED,
)
from platform.persistence.errors import BoundExceeded


class VerificationVerdict(StrEnum):
    """What a verification concluded. There is no sixth member.

    ``INCONCLUSIVE`` is the one that earns the closed set. A system that folded
    "the signal did not clearly get worse" into success would report a high
    success rate to an operator who had stopped believing it, and every other
    member here exists to keep that fold from being available.
    """

    #: The condition the action was taken against cleared.
    EFFECTIVE = VERIFICATION_EFFECTIVE
    #: The action ran, the signals were readable, and the condition still holds.
    INEFFECTIVE = VERIFICATION_INEFFECTIVE
    #: The signals moved the wrong way by more than the noise floor.
    WORSENED = VERIFICATION_WORSENED
    #: Nothing could be concluded — the resource went away, the signals were not
    #: readable, or they moved by less than it takes to tell.
    INCONCLUSIVE = VERIFICATION_INCONCLUSIVE
    #: The capability declares no signal its effect would appear in.
    UNVERIFIABLE = VERIFICATION_UNVERIFIABLE

    @property
    def is_success(self) -> bool:
        """Return whether this verdict closes an incident."""
        return self is VerificationVerdict.EFFECTIVE

    @property
    def escalates(self) -> bool:
        """Return whether this verdict sends the incident to a human.

        Everything that is not success, including ``INCONCLUSIVE``. An action
        whose effect nobody could measure is not an action anybody should close
        an incident on.
        """
        return self is not VerificationVerdict.EFFECTIVE


class VerificationState(StrEnum):
    """Where one obligation is in its own life. There is no fourth member."""

    #: Executed, settling, not yet read back. What every surface must say.
    AWAITING = "awaiting_verification"
    #: A worker holds it and is reading the signals now.
    CLAIMED = "claimed"
    #: A verdict was reached. Terminal.
    VERIFIED = "verified"

    @property
    def is_open(self) -> bool:
        """Return whether this obligation is still owed."""
        return self is not VerificationState.VERIFIED


class RollbackDisposition(StrEnum):
    """What happened to the action's rollback plan after the verdict.

    Five members because "we did not need to" and "we could not" are different
    facts about the same resource, and an operator deciding whether to touch it
    by hand needs to know which.
    """

    #: The verdict did not call for one. The ordinary case.
    NOT_REQUIRED = "not_required"
    #: Rolled back and the rollback itself verified.
    ROLLED_BACK = "rolled_back"
    #: The rollback ran and did not achieve what it said. The worst outcome
    #: this port records, and the one that suspends autonomy on the resource.
    FAILED = "failed"
    #: There was no derivable plan, or the world moved on and the plan no longer
    #: matches the target. Said explicitly rather than silently skipped.
    IMPOSSIBLE = "impossible"
    #: Rolled back because the kill switch engaged mid-flight, so the action
    #: reached a consistent state rather than being abandoned half-applied.
    INTERRUPTED = "interrupted"


@dataclass(frozen=True, slots=True)
class RemediationOutcome:
    """One action, the signals it was meant to move, and what they did.

    ``before`` is captured immediately prior to execution and ``after`` when the
    settle period has elapsed. Both are on the row rather than recomputed,
    because a verdict a human disagrees with is only arguable if the values it
    was reached from are still there.

    ``condition_key`` is what prompted the action — the detector, the alert, the
    incident's correlation key. It is the third dimension effectiveness is
    queried by, because "this restart works on this pod" and "this restart works
    when the pod is out of memory" are different claims and only the second one
    is useful to a proposal.
    """

    action_id: str
    capability: str
    resource_id: str
    executed_at: datetime
    due_at: datetime
    state: VerificationState = VerificationState.AWAITING
    verdict: VerificationVerdict | None = None
    condition_key: str = ""
    team_node_id: str = ""
    incident_id: str = ""
    run_id: str = ""
    plan_id: str = ""
    settle_seconds: int = 0
    #: The signals the capability declared its effect would appear in. Empty
    #: means the capability declared none, which is ``UNVERIFIABLE`` and a
    #: policy question rather than a defect.
    signal_names: tuple[str, ...] = ()
    before: Mapping[str, float] = field(default_factory=dict)
    after: Mapping[str, float] = field(default_factory=dict)
    verified_at: datetime | None = None
    detail: str = ""
    rollback: RollbackDisposition = RollbackDisposition.NOT_REQUIRED
    rollback_detail: str = ""
    autonomous: bool = False
    #: The plan that reverses this action and the action itself, in their stored
    #: forms. Carried on the row rather than looked up, because an automatic
    #: rollback happens after a settle period that may span a restart — and a
    #: rollback that could not be found would leave a change that made things
    #: worse in place, which is the one outcome this feature exists to undo.
    #: An autonomous action has no approval to read the plan back from, so there
    #: is no other durable place it could come from.
    undo: Mapping[str, Any] = field(default_factory=dict)
    #: How many times a worker has claimed this obligation. Counts claims, not
    #: verdicts, so a worker crashing repeatedly is visible as that.
    attempts: int = 0
    lease_holder: str = ""
    lease_expires_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.action_id:
            raise ValueError("A remediation outcome needs the action it records.")
        if not self.capability:
            raise ValueError("A remediation outcome needs the capability that acted.")
        if not self.resource_id:
            raise ValueError(
                "A remediation outcome needs the resource it acted on. Effectiveness is "
                "per resource, and a row with no resource joins no history."
            )
        if self.state is VerificationState.VERIFIED and self.verdict is None:
            raise ValueError(
                f"{self.action_id!r} is recorded as verified with no verdict. "
                f"'Verified' without one of the five outcomes is the shape in which "
                f"'we could not tell' silently reads as success."
            )

    @property
    def awaiting_verification(self) -> bool:
        """Return whether every surface must still say the result is unknown."""
        return self.state.is_open

    @property
    def pattern_key(self) -> str:
        """Return the key recurrence is counted against: this capability, here.

        Per resource *and* capability, per FR-020. A global count would raise a
        pattern the first busy week the deployment had, and a per-resource one
        would merge a restart and a scale into one story.
        """
        return f"{self.capability}@{self.resource_id}"


@dataclass(frozen=True, slots=True)
class EffectivenessQuery:
    """Every dimension the ledger can be sliced by.

    Empty tuples mean "no filter on this dimension" rather than "match nothing",
    for the reason ``EstateQuery`` gives: it is the only reading that composes
    when a caller builds a query out of optional inputs.
    """

    resource_ids: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    condition_keys: tuple[str, ...] = ()
    verdicts: tuple[VerificationVerdict, ...] = ()
    states: tuple[VerificationState, ...] = ()
    team_node_id: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    limit: int = 50


@dataclass(frozen=True, slots=True)
class EffectivenessSummary:
    """How often one thing has worked, as counts rather than as records.

    Counts, because this is read on the path of a proposal and the alternative
    is paging a year of history to compute a ratio. ``total`` includes the
    unverified, so a caller can tell "it has never worked" from "nothing has
    finished settling yet" — which are opposite recommendations.
    """

    total: int = 0
    counts: Mapping[VerificationVerdict, int] = field(default_factory=dict)
    awaiting: int = 0
    last_at: datetime | None = None
    last_verdict: VerificationVerdict | None = None

    @property
    def verified(self) -> int:
        """Return how many of these actions reached a verdict."""
        return sum(self.counts.values())

    @property
    def success_ratio(self) -> float:
        """Return the share of verdicts that were ``EFFECTIVE``, in ``[0, 1]``.

        Zero when nothing has been verified, rather than one. A capability with
        no history has not earned a recommendation, and vacuous perfection would
        put it above one that has worked four times out of five.
        """
        if self.verified <= 0:
            return 0.0
        return self.counts.get(VerificationVerdict.EFFECTIVE, 0) / self.verified


@dataclass(frozen=True, slots=True)
class RecurringProblem:
    """A pattern, not an occurrence: this keeps happening and a change is owed.

    Distinct from an incident in three ways the type enforces. It names a
    capability and a resource rather than a cause; it carries the actions it was
    derived from rather than subjects; and ``close_reason`` is required to close
    it, because the thing that closes a recurring problem is a change somebody
    made and "resolved" would record nothing about what.
    """

    problem_id: str
    pattern_key: str
    capability: str
    resource_id: str
    title: str
    summary: str
    raised_at: datetime
    occurrences: int
    window_seconds: int
    action_ids: tuple[str, ...] = ()
    team_node_id: str = ""
    incident_ids: tuple[str, ...] = ()
    #: Whether autonomous repetition of this capability here is suppressed.
    #: Set when the problem is raised and cleared when it is closed, so an
    #: operator has one thing to look at rather than two that can disagree.
    suppresses_autonomy: bool = True
    closed_at: datetime | None = None
    close_reason: str = ""
    closed_by: str = ""

    def __post_init__(self) -> None:
        if not self.pattern_key:
            raise ValueError(
                "A recurring problem needs the pattern it names. Without one the fifth "
                "occurrence raises a second problem about the first."
            )
        if self.closed_at is not None and not self.close_reason.strip():
            raise ValueError(
                f"{self.problem_id!r} is closed with no reason. A recurring problem is "
                f"closed by a change, and a close that does not say which change is a "
                f"record that the problem stopped being displayed."
            )

    @property
    def is_live(self) -> bool:
        """Return whether this pattern is still somebody's problem."""
        return self.closed_at is None

    @property
    def suppressing(self) -> bool:
        """Return whether autonomous repetition here is currently suppressed."""
        return self.is_live and self.suppresses_autonomy


def check_effectiveness_limit(limit: int) -> int:
    """Return ``limit``, or raise if it exceeds the effectiveness page bound."""
    if limit > MAX_EFFECTIVENESS_PAGE_SIZE:
        raise BoundExceeded(
            parameter="limit",
            requested=limit,
            limit=MAX_EFFECTIVENESS_PAGE_SIZE,
            constant="MAX_EFFECTIVENESS_PAGE_SIZE",
        )
    if limit < 1:
        raise ValueError(f"limit must be at least 1, got {limit}.")
    return limit


def check_problem_limit(limit: int) -> int:
    """Return ``limit``, or raise if it exceeds the recurring-problem page bound."""
    if limit > MAX_RECURRING_PROBLEM_PAGE_SIZE:
        raise BoundExceeded(
            parameter="limit",
            requested=limit,
            limit=MAX_RECURRING_PROBLEM_PAGE_SIZE,
            constant="MAX_RECURRING_PROBLEM_PAGE_SIZE",
        )
    if limit < 1:
        raise ValueError(f"limit must be at least 1, got {limit}.")
    return limit


def check_claim_batch(limit: int) -> int:
    """Return ``limit``, or raise if it exceeds the claim batch bound."""
    if limit > MAX_VERIFICATION_CLAIM_BATCH:
        raise BoundExceeded(
            parameter="limit",
            requested=limit,
            limit=MAX_VERIFICATION_CLAIM_BATCH,
            constant="MAX_VERIFICATION_CLAIM_BATCH",
        )
    if limit < 1:
        raise ValueError(f"limit must be at least 1, got {limit}.")
    return limit


def matches(row: RemediationOutcome, query: EffectivenessQuery) -> bool:
    """Return whether ``row`` satisfies every filter ``query`` declares.

    Shared by both backends because it is contract: a capability filter that
    matched a prefix in one and an exact string in the other would make a
    proposal read one history in memory and another in PostgreSQL.
    """
    if query.resource_ids and row.resource_id not in query.resource_ids:
        return False
    if query.capabilities and row.capability not in query.capabilities:
        return False
    if query.condition_keys and row.condition_key not in query.condition_keys:
        return False
    if query.verdicts and row.verdict not in query.verdicts:
        return False
    if query.states and row.state not in query.states:
        return False
    if query.team_node_id is not None and row.team_node_id != query.team_node_id:
        return False
    if query.since is not None and row.executed_at < query.since:
        return False
    return not (query.until is not None and row.executed_at > query.until)


def summarise(rows: tuple[RemediationOutcome, ...]) -> EffectivenessSummary:
    """Return the aggregate ``rows`` describe.

    Shared, so the in-memory backend and the SQL one cannot disagree about what
    a ratio means. The SQL implementation counts in the database and assembles
    the same value; this is what it is held against.
    """
    counts: dict[VerificationVerdict, int] = {}
    awaiting = 0
    latest: RemediationOutcome | None = None
    for row in rows:
        if row.verdict is not None and row.state is VerificationState.VERIFIED:
            counts[row.verdict] = counts.get(row.verdict, 0) + 1
        if row.awaiting_verification:
            awaiting += 1
        if latest is None or row.executed_at > latest.executed_at:
            latest = row
    return EffectivenessSummary(
        total=len(rows),
        counts=counts,
        awaiting=awaiting,
        last_at=latest.executed_at if latest is not None else None,
        last_verdict=latest.verdict if latest is not None else None,
    )


@runtime_checkable
class RemediationLedger(Protocol):
    """One organisation's remediation outcomes and patterns, inside one transaction."""

    async def record(self, outcome: RemediationOutcome) -> RemediationOutcome:
        """Store ``outcome``, replacing any earlier row for the same action.

        Keyed by the action rather than generated, so an executor that retried
        writes one obligation. Two obligations for one action would be two
        verifications, two verdicts, and — for a worsened change — two
        rollbacks.
        """

    async def get(self, action_id: str) -> RemediationOutcome | None:
        """Return the outcome recorded for ``action_id``, or ``None``."""

    async def claim_due(
        self,
        *,
        now: datetime,
        worker_id: str,
        lease_seconds: float = VERIFICATION_LEASE_SECONDS,
        limit: int = MAX_VERIFICATION_CLAIM_BATCH,
    ) -> tuple[RemediationOutcome, ...]:
        """Claim up to ``limit`` obligations due at ``now``, and return them.

        Claiming is atomic per obligation: two workers calling this concurrently
        divide the due obligations between them and never both receive one.
        Verified rows are never returned, and a row whose lease has not expired
        belongs to whoever holds it. Each returned row has its ``attempts``
        incremented and its lease stamped. Raises ``BoundExceeded`` above
        ``MAX_VERIFICATION_CLAIM_BATCH``.
        """

    async def history(self, query: EffectivenessQuery) -> tuple[RemediationOutcome, ...]:
        """Return the outcomes matching ``query``, most recently executed first.

        Raises ``BoundExceeded`` above ``MAX_EFFECTIVENESS_PAGE_SIZE``.
        """

    async def effectiveness(self, query: EffectivenessQuery) -> EffectivenessSummary:
        """Return the counts matching ``query``, over however much history there is.

        Unbounded by page size, deliberately, because it is a count. This is the
        one read on the path of a proposal, so it answers with an aggregate the
        database computes rather than with rows a caller adds up.
        """

    async def upsert_problem(self, problem: RecurringProblem) -> RecurringProblem:
        """Store ``problem``, replacing any earlier record with the same id."""

    async def open_problem_for(self, pattern_key: str) -> RecurringProblem | None:
        """Return the *live* problem for ``pattern_key``, or ``None``.

        Live rather than most-recent, for the reason ``IncidentStore.open_for``
        gives: a pattern that was dealt with and closed must not silently absorb
        next quarter's recurrence.
        """

    async def problems(
        self,
        *,
        live_only: bool = True,
        limit: int = MAX_RECURRING_PROBLEM_PAGE_SIZE,
    ) -> tuple[RecurringProblem, ...]:
        """Return recurring problems, most recently raised first.

        Raises ``BoundExceeded`` above ``MAX_RECURRING_PROBLEM_PAGE_SIZE``.
        """

    async def purge(self, *, before: datetime) -> int:
        """Delete verified outcomes executed before ``before`` and return how many.

        Only verified ones. An obligation still owed is a verification the
        deployment promised, whatever its age, and a sweep that removed one
        would leave an action reported as awaiting verification forever.
        """


__all__ = [
    "EffectivenessQuery",
    "EffectivenessSummary",
    "RecurringProblem",
    "RemediationLedger",
    "RemediationOutcome",
    "RollbackDisposition",
    "VerificationState",
    "VerificationVerdict",
    "check_claim_batch",
    "check_effectiveness_limit",
    "check_problem_limit",
    "matches",
    "summarise",
]
