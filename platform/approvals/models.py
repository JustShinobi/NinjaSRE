"""One queued change, whatever kind of change it is.

Five things go through this queue — a configuration edit, a prompt change, a
capability toggle, an agent's knowledge proposal, and a production remediation —
and they are one type here rather than five. They have the same shape: somebody
proposed something, somebody else decides, and the record has to say what was
decided against. Five types would have drifted, and the one nobody looked at
twice would be the weakest.

**The fingerprint is what makes an approval mean something.** It is taken of the
target's *current* state at the moment the change is queued, and compared again
at the moment somebody approves. A reviewer looking at a two-day-old diff is
looking at a description of state that may no longer exist, and approving it
would apply a change against a reality they never saw. That is the specific way
approval workflows produce incidents, and ``fingerprint_of`` exists to make it
detectable rather than to make it unlikely.

**``current`` is stored, not re-read.** The proposed value and the value it was
proposed against both live on the record. Reconstructing "what did this change
look like" from the target's present state would answer a different question
every time it was asked, and the audit trail's job is to answer the same one
forever.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Final

from config.constants.security import (
    APPROVAL_PAYLOAD_RUN,
    CHANGE_TYPE_CAPABILITY,
    CHANGE_TYPE_CONFIGURATION,
    CHANGE_TYPE_KNOWLEDGE,
    CHANGE_TYPE_PROMPT,
    CHANGE_TYPE_REMEDIATION,
    PENDING_CHANGE_EXPIRY_HOURS,
    SIDE_EFFECT_WRITE_REVERSIBLE,
)
from platform.persistence.ports.approval_store import ApprovalRequest, ApprovalState


class ChangeType(StrEnum):
    """What kind of thing is being changed.

    The type decides three things and nothing else: which diff renderer runs,
    which applier applies it, and whether the organisation's policy gates it.
    Everything else about a queued change is the same whichever type it is.
    """

    CONFIGURATION = CHANGE_TYPE_CONFIGURATION
    PROMPT = CHANGE_TYPE_PROMPT
    CAPABILITY = CHANGE_TYPE_CAPABILITY
    KNOWLEDGE = CHANGE_TYPE_KNOWLEDGE
    REMEDIATION = CHANGE_TYPE_REMEDIATION


class ChangeState(StrEnum):
    """Where a queued change got to.

    ``CONFLICTED`` is undecided, not final. A conflicted change is one a
    reviewer still has to answer — they just have to answer it against the
    target's current state rather than the state it was queued against. Making
    it terminal would mean an operator's edit disappeared because somebody else
    touched a neighbouring field.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CONFLICTED = "conflicted"

    @property
    def is_decided(self) -> bool:
        """Return whether this state is final and no further decision applies."""
        return self in _DECIDED_STATES

    @property
    def is_open(self) -> bool:
        """Return whether this change is still waiting on a human."""
        return not self.is_decided


_DECIDED_STATES: Final[frozenset[ChangeState]] = frozenset(
    {ChangeState.APPROVED, ChangeState.REJECTED, ChangeState.EXPIRED}
)


class ConflictReason(StrEnum):
    """Why a queued change stopped describing reality."""

    #: Somebody changed the target between queuing and the decision.
    TARGET_CHANGED = "target_changed"
    #: Another change to the same target was approved first.
    SIBLING_APPROVED = "sibling_approved"
    #: The target no longer exists, so there is nothing to apply this to.
    TARGET_DELETED = "target_deleted"


#: The fingerprint of a target that is not there. A distinct value rather than
#: ``None`` so "the node was deleted" and "the fingerprint was never taken"
#: cannot be confused by anything comparing two strings.
ABSENT_FINGERPRINT: Final = "absent"


def fingerprint_of(value: Any) -> str:
    """Return a stable fingerprint of ``value``, or ``ABSENT_FINGERPRINT`` for nothing.

    Canonical JSON with sorted keys, then SHA-256. Sorted because two documents
    that differ only in key order are the same configuration, and a fingerprint
    that disagreed would mark every reordered write as a conflict — which is how
    a conflict check trains its reviewers to ignore it.
    """
    if value is None:
        return ABSENT_FINGERPRINT
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ChangeTarget:
    """What is being changed, and where in the hierarchy it takes effect.

    ``node_id`` is separate from ``identifier`` because two different questions
    are asked of it. The identifier says which thing to apply the change to; the
    node says who may review it and which teams inherit the result. For a
    configuration change they are the same string, and for a capability toggle
    or a knowledge document they are not.
    """

    identifier: str
    node_id: str | None = None
    #: The field within the target, when the change is to one field rather than
    #: to the whole thing. Configuration edits set it; a knowledge proposal does
    #: not, because the document is the unit.
    path: str | None = None

    def __post_init__(self) -> None:
        if not self.identifier:
            raise ValueError("A change target needs the identifier of the thing it changes.")

    def __str__(self) -> str:
        """Return the target as one line a reviewer can read."""
        return f"{self.identifier}:{self.path}" if self.path else self.identifier


@dataclass(frozen=True, slots=True)
class Decision:
    """Approve or reject, with who, when, and why.

    The reason is optional on an approval and required in practice on a
    rejection — ``PendingChange.rejected`` is what carries it back to the
    requester, and a rejection whose reason was dropped is one the requester
    re-submits unchanged.
    """

    approved: bool
    decided_by: str
    decided_at: datetime
    reason: str | None = None

    def to_record(self) -> dict[str, Any]:
        """Return the stored form of this decision."""
        return {
            "approved": self.approved,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at.isoformat(),
            "reason": self.reason,
        }

    @classmethod
    def of_record(cls, record: Mapping[str, Any]) -> Decision:
        """Return the decision a stored record describes."""
        return cls(
            approved=bool(record.get("approved", False)),
            decided_by=str(record.get("decided_by", "")),
            decided_at=datetime.fromisoformat(str(record["decided_at"])),
            reason=_optional_str(record.get("reason")),
        )


@dataclass(frozen=True, slots=True)
class Conflict:
    """A detected divergence between what was queued and what is there now.

    Carries both fingerprints. A reviewer being told "this changed" needs to be
    able to tell a genuine second edit from a re-queue of the same value, and
    two hashes are what makes that a comparison rather than a belief.
    """

    reason: ConflictReason
    detected_at: datetime
    detail: str
    expected_fingerprint: str
    observed_fingerprint: str = ABSENT_FINGERPRINT

    @property
    def is_recoverable(self) -> bool:
        """Return whether a re-review could still lead to an approval.

        A deleted target is not recoverable: there is nothing left to apply the
        change to, and re-reviewing it would produce an approval that could
        never be honoured.
        """
        return self.reason is not ConflictReason.TARGET_DELETED

    def to_record(self) -> dict[str, Any]:
        """Return the stored form of this conflict."""
        return {
            "reason": self.reason.value,
            "detected_at": self.detected_at.isoformat(),
            "detail": self.detail,
            "expected_fingerprint": self.expected_fingerprint,
            "observed_fingerprint": self.observed_fingerprint,
        }

    @classmethod
    def of_record(cls, record: Mapping[str, Any]) -> Conflict:
        """Return the conflict a stored record describes."""
        return cls(
            reason=ConflictReason(str(record.get("reason", ConflictReason.TARGET_CHANGED.value))),
            detected_at=datetime.fromisoformat(str(record["detected_at"])),
            detail=str(record.get("detail", "")),
            expected_fingerprint=str(record.get("expected_fingerprint", ABSENT_FINGERPRINT)),
            observed_fingerprint=str(record.get("observed_fingerprint", ABSENT_FINGERPRINT)),
        )


# --- The payload keys --------------------------------------------------------
#
# Named rather than spelled inline. The store holds a queued change as an
# ``ApprovalRequest``'s ``arguments``, and a second spelling of one of these
# keys is a change that reads back with a field missing and no error anywhere.

CHANGE_TYPE_KEY: Final = "change_type"
TARGET_KEY: Final = "target"
NODE_KEY: Final = "node_id"
PATH_KEY: Final = "path"
PROPOSED_KEY: Final = "proposed"
CURRENT_KEY: Final = "current"
REQUESTER_KEY: Final = "requester"
RATIONALE_KEY: Final = "rationale"
FINGERPRINT_KEY: Final = "fingerprint"
STATE_KEY: Final = "state"
DECISION_KEY: Final = "decision"
CONFLICT_KEY: Final = "conflict"


@dataclass(frozen=True, slots=True)
class PendingChange:
    """A proposed change waiting on a human, and everything the decision needs.

    Frozen. Every transition returns a new value through the state machine, so
    there is no method here that moves a change forward — a change that could
    approve itself would make the service's monopoly on transitions a
    convention rather than a property.
    """

    change_id: str
    change_type: ChangeType
    target: ChangeTarget
    proposed: Mapping[str, Any]
    current: Mapping[str, Any]
    requester: str
    rationale: str
    created_at: datetime
    expires_at: datetime
    fingerprint: str
    state: ChangeState = ChangeState.PENDING
    side_effect_level: str = SIDE_EFFECT_WRITE_REVERSIBLE
    decision: Decision | None = None
    conflict: Conflict | None = None

    def __post_init__(self) -> None:
        if not self.change_id:
            raise ValueError("A queued change needs an identifier.")
        if not self.requester:
            raise ValueError("A queued change needs the principal who requested it.")
        if self.expires_at <= self.created_at:
            raise ValueError(
                f"{self.change_id!r} expires at or before it was created. A change that is "
                f"already expired when it is queued is one nobody can answer."
            )

    @classmethod
    def queued(
        cls,
        *,
        change_id: str,
        change_type: ChangeType,
        target: ChangeTarget,
        proposed: Mapping[str, Any],
        current: Mapping[str, Any] | None,
        requester: str,
        rationale: str,
        at: datetime,
        expiry_hours: float = PENDING_CHANGE_EXPIRY_HOURS,
        side_effect_level: str = SIDE_EFFECT_WRITE_REVERSIBLE,
    ) -> PendingChange:
        """Return a change queued at ``at``, fingerprinted against ``current``.

        The fingerprint is taken here rather than by the caller. A caller that
        supplied its own could supply one taken before it read the target, and
        the whole point of the fingerprint is that it describes the state the
        reviewer will be shown.
        """
        return cls(
            change_id=change_id,
            change_type=change_type,
            target=target,
            proposed=dict(proposed),
            current=dict(current) if current is not None else {},
            requester=requester,
            rationale=rationale,
            created_at=at,
            expires_at=at + timedelta(hours=expiry_hours),
            fingerprint=fingerprint_of(current),
            side_effect_level=side_effect_level,
        )

    # --- Reading -------------------------------------------------------------

    @property
    def proposing_run(self) -> str:
        """Return the run that proposed this change, or empty when none did.

        Read from the payload rather than held as a field, because the payload
        is what the proposer already fills in and a second copy is a second
        thing to keep true. A change queued by a person carries no run and
        answers with the empty string, which is the honest answer rather than
        an invented identifier.
        """
        found = self.proposed.get(APPROVAL_PAYLOAD_RUN)
        return found if isinstance(found, str) else ""

    @property
    def node_id(self) -> str | None:
        """Return the node this change takes effect at, if it names one."""
        return self.target.node_id

    @property
    def is_open(self) -> bool:
        """Return whether this change is still waiting on a human."""
        return self.state.is_open

    @property
    def approved(self) -> bool:
        """Return whether this change was approved and applied."""
        return self.state is ChangeState.APPROVED

    @property
    def rejection_reason(self) -> str | None:
        """Return why this was rejected, for the requester to read."""
        if self.state is not ChangeState.REJECTED or self.decision is None:
            return None
        return self.decision.reason

    def has_expired(self, now: datetime) -> bool:
        """Return whether this change's answering window has closed."""
        return self.is_open and now >= self.expires_at

    def matches(self, observed: Any) -> bool:
        """Return whether the target still looks the way it did at queue time."""
        return fingerprint_of(observed) == self.fingerprint

    def summary(self) -> str:
        """Return the one line a notification and a queue listing show."""
        return f"{self.change_type.value} change to {self.target} requested by {self.requester}"

    # --- Building the next value ---------------------------------------------
    #
    # Deliberately not transitions. Each returns a value with the state already
    # decided by the caller; `state_machine.advance` is what decides whether the
    # caller was allowed to, and `service` is the only caller.

    def with_state(self, state: ChangeState) -> PendingChange:
        """Return this change in ``state``, everything else unchanged."""
        return replace(self, state=state)

    def decided(self, decision: Decision) -> PendingChange:
        """Return this change carrying ``decision`` and the state it implies."""
        return replace(
            self,
            state=ChangeState.APPROVED if decision.approved else ChangeState.REJECTED,
            decision=decision,
            conflict=None if decision.approved else self.conflict,
        )

    def conflicting(self, conflict: Conflict) -> PendingChange:
        """Return this change marked conflicted, carrying why."""
        return replace(self, state=ChangeState.CONFLICTED, conflict=conflict)

    def rereviewed(self, *, against: Any, at: datetime) -> PendingChange:
        """Return this change back in review against the target's current state.

        Re-fingerprinted against what is there *now*, and the stored ``current``
        replaced with it. Leaving the old fingerprint would put the change
        straight back into conflict on the next decision; leaving the old
        ``current`` would show the reviewer a diff against state nobody has.
        """
        return replace(
            self,
            state=ChangeState.PENDING,
            current=dict(against) if isinstance(against, Mapping) else {},
            fingerprint=fingerprint_of(against),
            conflict=None,
            created_at=self.created_at,
            expires_at=max(self.expires_at, at),
        )

    # --- Storage -------------------------------------------------------------

    def to_request(self) -> ApprovalRequest:
        """Return the store record this change is held as.

        ``CONFLICTED`` maps onto the store's ``PENDING``, which is correct
        rather than lossy: a conflicted change is undecided, and a listing of
        what still needs answering must include it. Why it is conflicted lives
        in the payload, where re-review can clear it without the store having to
        offer a way back out of a decided state.

        ``run_id`` is the run that proposed this change when one did, and the
        key built from the target when none did. A configuration edit is queued
        by a person and has no run to name, so for those the synthesised key is
        the answer — it is how a listing groups changes to one target. A
        remediation is proposed by an investigation, and that run is the only
        thing any surface can find the approval by: ``incident-detail`` reads
        ``/v1/approvals?run_id=<the incident's run>`` and draws the approve and
        reject controls only when it comes back with something. Writing
        ``remediation:pve01`` into the column while the real run sat in the
        payload meant that query never matched, so the controls were never
        drawn and no proposal in this product could ever be decided.
        """
        return ApprovalRequest(
            approval_id=self.change_id,
            run_id=self.proposing_run or f"{self.change_type.value}:{self.target.identifier}",
            action=f"{self.change_type.value}.change",
            side_effect_level=self.side_effect_level,
            summary=self.summary(),
            requested_at=self.created_at,
            expires_at=self.expires_at,
            arguments=self.to_arguments(),
            state=_STORE_STATES[self.state],
            decided_at=self.decision.decided_at if self.decision else None,
            decided_by=self.decision.decided_by if self.decision else None,
            reason=self.decision.reason if self.decision else None,
        )

    def to_arguments(self) -> dict[str, Any]:
        """Return the payload the store holds this change's own fields in."""
        payload: dict[str, Any] = {
            CHANGE_TYPE_KEY: self.change_type.value,
            TARGET_KEY: self.target.identifier,
            NODE_KEY: self.target.node_id,
            PATH_KEY: self.target.path,
            PROPOSED_KEY: dict(self.proposed),
            CURRENT_KEY: dict(self.current),
            REQUESTER_KEY: self.requester,
            RATIONALE_KEY: self.rationale,
            FINGERPRINT_KEY: self.fingerprint,
            STATE_KEY: self.state.value,
        }
        if self.decision is not None:
            payload[DECISION_KEY] = self.decision.to_record()
        if self.conflict is not None:
            payload[CONFLICT_KEY] = self.conflict.to_record()
        return payload

    @classmethod
    def of_request(cls, request: ApprovalRequest) -> PendingChange:
        """Return the change ``request`` stores.

        The store's state wins for the three final ones and the payload's wins
        while the change is open. Expiry is the reason: ``expire_due`` moves a
        row to ``EXPIRED`` without going through this package, and a payload
        still reading ``pending`` must not resurrect it.
        """
        payload = request.arguments
        stored = ApprovalState(request.state)
        state = (
            _PAYLOAD_STATES[stored]
            if stored is not ApprovalState.PENDING
            else ChangeState(str(payload.get(STATE_KEY, ChangeState.PENDING.value)))
        )
        decision = payload.get(DECISION_KEY)
        conflict = payload.get(CONFLICT_KEY)
        return cls(
            change_id=request.approval_id,
            change_type=ChangeType(str(payload.get(CHANGE_TYPE_KEY, ChangeType.CONFIGURATION))),
            target=ChangeTarget(
                identifier=str(payload.get(TARGET_KEY, request.approval_id)),
                node_id=_optional_str(payload.get(NODE_KEY)),
                path=_optional_str(payload.get(PATH_KEY)),
            ),
            proposed=_mapping(payload.get(PROPOSED_KEY)),
            current=_mapping(payload.get(CURRENT_KEY)),
            requester=str(payload.get(REQUESTER_KEY, "")),
            rationale=str(payload.get(RATIONALE_KEY, "")),
            created_at=request.requested_at,
            expires_at=request.expires_at,
            fingerprint=str(payload.get(FINGERPRINT_KEY, ABSENT_FINGERPRINT)),
            state=state,
            side_effect_level=request.side_effect_level,
            decision=Decision.of_record(decision) if isinstance(decision, Mapping) else None,
            conflict=Conflict.of_record(conflict) if isinstance(conflict, Mapping) else None,
        )


#: How each state is held in the store. Both open states map onto ``PENDING``,
#: because the store's vocabulary is "decided or not" and both of ours are not.
_STORE_STATES: Final[Mapping[ChangeState, ApprovalState]] = {
    ChangeState.PENDING: ApprovalState.PENDING,
    ChangeState.CONFLICTED: ApprovalState.PENDING,
    ChangeState.APPROVED: ApprovalState.APPROVED,
    ChangeState.REJECTED: ApprovalState.REJECTED,
    ChangeState.EXPIRED: ApprovalState.EXPIRED,
}

#: The reverse, for the three the store decides on its own.
_PAYLOAD_STATES: Final[Mapping[ApprovalState, ChangeState]] = {
    ApprovalState.PENDING: ChangeState.PENDING,
    ApprovalState.APPROVED: ChangeState.APPROVED,
    ApprovalState.REJECTED: ChangeState.REJECTED,
    ApprovalState.EXPIRED: ChangeState.EXPIRED,
}


@dataclass(frozen=True, slots=True)
class ReviewerSet:
    """The principals eligible to decide one change, and who was excluded.

    ``excluded`` is carried rather than dropped. A queue with no eligible
    reviewer is a change nobody can answer, and "the only person who could
    approve it is the person who asked" is an answer an operator can act on
    where an empty list is not.
    """

    change_id: str
    reviewers: tuple[str, ...] = field(default_factory=tuple)
    excluded: Mapping[str, str] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        """Return whether nobody can decide this change as things stand."""
        return not self.reviewers

    def allows(self, principal_id: str) -> bool:
        """Return whether ``principal_id`` is in the eligible set."""
        return principal_id in self.reviewers


def _mapping(value: Any) -> dict[str, Any]:
    """Return ``value`` as a plain dict, or an empty one if it is not a mapping."""
    return dict(value) if isinstance(value, Mapping) else {}


def _optional_str(value: Any) -> str | None:
    """Return ``value`` as a string, or ``None`` when it is absent or empty."""
    if value is None:
        return None
    text = str(value)
    return text if text else None


__all__ = [
    "ABSENT_FINGERPRINT",
    "ChangeState",
    "ChangeTarget",
    "ChangeType",
    "Conflict",
    "ConflictReason",
    "Decision",
    "PendingChange",
    "ReviewerSet",
    "fingerprint_of",
]
