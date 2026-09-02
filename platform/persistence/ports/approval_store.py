"""Approvals and the rollback plans without which none of them may be granted.

Article III says an action above read needs per-action human approval *and* a
stored rollback plan. The "and" is enforced here rather than trusted: ``decide``
refuses to record an approval for a request that has no rollback plan stored,
and raises. A deployment can therefore not reach a state where something
irreversible was authorised and nobody wrote down how to undo it — not because
the calling code is careful, but because the store will not hold that state.

Requests expire. An approval nobody answered during the incident must not still
be answerable a week later, when the operator clicking it has forgotten what
the cluster looked like. ``expire_due`` is what a caller runs to move those to
``EXPIRED``, and a request that has expired is decided: it cannot come back.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

#: Where a request raised to replace an expired one records which one it came
#: from — a key at the top level of ``arguments``, never a column of its own.
#: Named here rather than where the value is written, because three things read
#: it and each would otherwise spell it for itself: ``pending_for_origin``
#: filters on it, ``create_request`` refuses a second live row carrying it, and
#: PostgreSQL's ``ix_approvals_pending_origin`` indexes it. A writer and a
#: filter that spell it two ways is a lookup answering ``None`` for ever, with
#: nothing anywhere reporting an error.
#:
#: Top level, and written by the insert that creates the request, because a
#: partial unique index can only be stated over a value already in the
#: statement that writes the row. A marker applied by a later amendment leaves
#: a committed proposal carrying none, which is precisely the window two
#: concurrent reproposals used to both fit through.
ORIGIN_APPROVAL_ID_KEY = "origin_approval_id"


class ApprovalState(StrEnum):
    """Where an approval request got to."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    #: Withdrawn by a person rather than answered — today only reachable from
    #: ``EXPIRED``, never from a request still within its own window. Distinct
    #: from ``REJECTED``: nobody said no to the action, the window to say
    #: anything at all closed first.
    DISCARDED = "discarded"

    @property
    def is_decided(self) -> bool:
        """Return whether this state is final."""
        return self is not ApprovalState.PENDING


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    """One proposed action, awaiting a human.

    ``arguments`` is the call as it would be made, stored verbatim. An approval
    for "restart the checkout deployment" that was granted against different
    arguments than the ones executed is not an approval, and keeping the exact
    call is what lets the audit trail prove they matched.
    """

    approval_id: str
    run_id: str
    action: str
    side_effect_level: str
    summary: str
    requested_at: datetime
    expires_at: datetime
    arguments: Mapping[str, Any] = field(default_factory=dict)
    state: ApprovalState = ApprovalState.PENDING
    decided_at: datetime | None = None
    decided_by: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class RollbackStep:
    """One step of undoing an action, as a capability call."""

    ordinal: int
    description: str
    capability: str
    arguments: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RollbackPlan:
    """How to undo the action an approval would authorise.

    Steps are ordered as they would be executed, which for an undo is the
    reverse of how the action was applied. Storing them ordered rather than
    sorting at execution time keeps the ordering decision with the person who
    understood the action.
    """

    plan_id: str
    approval_id: str
    steps: tuple[RollbackStep, ...] = ()
    created_at: datetime | None = None
    notes: str | None = None


@runtime_checkable
class ApprovalStore(Protocol):
    """Approval requests and rollback plans, within one tenant."""

    async def create_request(self, request: ApprovalRequest) -> ApprovalRequest:
        """Store a pending request and return it.

        Raises ``DuplicateRecord`` if ``approval_id`` already exists.
        """

    async def get_request(self, approval_id: str) -> ApprovalRequest | None:
        """Return the request with ``approval_id``, or ``None``."""

    async def decide(
        self,
        approval_id: str,
        *,
        state: ApprovalState,
        decided_by: str,
        decided_at: datetime,
        reason: str | None = None,
    ) -> ApprovalRequest:
        """Record a decision and return the request as stored.

        Raises ``RecordNotFound`` for an unknown request, ``AppendOnlyViolation``
        for one that is already decided — a decision is made once — and
        ``RecordNotFound`` naming the rollback plan when ``state`` is
        ``APPROVED`` and none has been stored (Article III).
        """

    async def amend_request(
        self, approval_id: str, *, arguments: Mapping[str, Any]
    ) -> ApprovalRequest:
        """Replace an undecided request's ``arguments`` and return it as stored.

        The one thing about a request that may change while it waits, and it may
        change only while it waits: a request that has been decided is refused
        with ``AppendOnlyViolation``, because rewriting the call after somebody
        approved it changes what they approved.

        This exists for the reviews that outlive the state they were raised
        against. A change queued on Monday and approved on Wednesday may have to
        record that the target moved in between, and be re-raised against what
        the target says now — neither of which is a decision, and neither of
        which should require discarding the request and losing its history.

        Raises ``RecordNotFound`` for an unknown request.
        """

    async def list_pending(
        self,
        *,
        run_id: str | None = None,
        limit: int = 50,
    ) -> tuple[ApprovalRequest, ...]:
        """Return undecided requests, oldest first — longest-waiting first."""

    async def pending_for_origin(self, approval_id: str) -> ApprovalRequest | None:
        """Return the undecided request raised to replace ``approval_id``, or ``None``.

        A lookup rather than something a caller filters out of ``list_pending``,
        and the difference is correctness rather than speed. A replacement is
        stamped with the instant it was raised, so it is the newest thing
        waiting, while pending requests are read oldest first — any bounded page
        of the queue stops containing it as soon as a page's worth of older
        requests sits ahead of it. Asking "is one of these the replacement for
        that origin" therefore answers "no" for a queue that is merely busy, at
        every page size, and the caller then raises a second live proposal for
        one expired decision.

        Only an undecided one counts. Once the replacement has itself been
        answered or has lapsed, its origin has nothing outstanding against it
        and may be proposed again; a lookup that still returned the answered
        one would make the second expiry unreproposable for ever.

        The oldest wins when more than one exists — a state nothing should be
        able to reach, and one an ordered answer at least makes the same on
        every read rather than whichever row the database happened to return.
        """

    async def list_decided(
        self,
        *,
        action: str | None = None,
        states: Sequence[ApprovalState] | None = None,
        limit: int = 50,
    ) -> tuple[ApprovalRequest, ...]:
        """Return answered requests, most recently decided first.

        The counterpart of ``list_pending``, and it exists because a decision is
        evidence rather than an ending. Two readers need it: the queue that shows
        a recurring proposal what was said the last three times it was refused,
        and the figure that says how many proposals this team accepts. Both are
        about the *history* of deciding, which nothing else in this port exposes.

        Ordered by decision rather than by request, because "what was said most
        recently" is the question, and expired rows carry a decision instant too.

        ``states`` narrows to exactly the states named — ``None`` keeps every
        non-``PENDING`` row, the behaviour this had before the parameter
        existed. A caller separating "expired, waiting on a repropose" from
        "answered by a person" (``approved``/``rejected``/``discarded``) reads
        two different pages of the same, otherwise-identical ordering rather
        than one page it would have to split itself.
        """

    async def discard(
        self,
        approval_id: str,
        *,
        discarded_by: str,
        discarded_at: datetime,
    ) -> ApprovalRequest:
        """Move ``approval_id`` to ``DISCARDED`` and return it as stored.

        Reachable from ``PENDING`` or ``EXPIRED`` — never from a request a
        person has already answered (``APPROVED``/``REJECTED``) or discarded
        once already. Raises ``RecordNotFound`` for an unknown request and
        ``AppendOnlyViolation`` for one already answered by a person. A
        transition, exactly like ``decide`` and ``expire_due``: the row is
        marked, never removed.
        """

    async def expire_due(self, now: datetime) -> tuple[ApprovalRequest, ...]:
        """Move every pending request past its expiry to ``EXPIRED``, and return them."""

    async def store_rollback_plan(self, plan: RollbackPlan) -> RollbackPlan:
        """Store the plan for an approval and return it.

        Raises ``RecordNotFound`` when the approval does not exist, and
        ``AppendOnlyViolation`` when it has already been decided: rewriting the
        undo procedure after somebody approved the action changes what they
        approved.
        """

    async def rollback_plan_for(self, approval_id: str) -> RollbackPlan | None:
        """Return the stored rollback plan for ``approval_id``, or ``None``."""

    async def record_rollback_executed(
        self,
        plan_id: str,
        *,
        executed_at: datetime,
        completed_steps: Sequence[int],
    ) -> RollbackPlan:
        """Record which steps of a rollback actually ran, and return the plan.

        Partial rollbacks are the normal case when something has gone wrong
        twice, and knowing which steps completed is the difference between a
        safe retry and a second incident.
        """


__all__ = [
    "ORIGIN_APPROVAL_ID_KEY",
    "ApprovalRequest",
    "ApprovalState",
    "ApprovalStore",
    "RollbackPlan",
    "RollbackStep",
]
