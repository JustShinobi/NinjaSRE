"""What this package raises, named so a caller can tell the cases apart.

Every type here is a different thing gone wrong at a review, and each one has a
different next step. A conflicted change needs re-reviewing against what the
target says now; a self-approval refusal needs a second person; a lost
permission needs a grant. Collapsing them into one "cannot approve" would leave
the reviewer with a wall instead of an instruction.

**A refusal never quotes a proposed value.** The diff is filtered through the
guardrail engine before anybody sees it, and an exception message is one of the
places "anybody" includes — a refusal that echoed a secret somebody tried to put
in configuration would put it in the log the refusal was keeping it out of.
"""

from __future__ import annotations

from collections.abc import Sequence


class ApprovalError(Exception):
    """Base for every failure raised by the approval layer."""


# --- The state machine -------------------------------------------------------


class IllegalTransition(ApprovalError):
    """Something asked for a state change the machine does not have.

    Raised rather than tolerated. A change that reached ``approved`` from
    ``expired`` is a change nobody decided on, and the only place to catch that
    is the transition itself.
    """

    def __init__(self, change_id: str, current: str, target: str) -> None:
        super().__init__(
            f"A change cannot go from {current!r} to {target!r} ({change_id!r}). "
            f"That transition is not in the machine."
        )
        self.change_id = change_id
        self.current = current
        self.target = target


class ChangeNotFound(ApprovalError):
    """Something named a queued change that does not exist in this tenant."""

    def __init__(self, change_id: str) -> None:
        super().__init__(f"No queued change {change_id!r} exists in this organisation.")
        self.change_id = change_id


class ChangeExpired(ApprovalError):
    """A decision arrived after the window for making it had closed.

    Its own error rather than ``ChangeAlreadyDecided``, because the two say
    different things to the person who clicked. "Somebody already decided this"
    means look at what they decided. "The window closed" means the diagram this
    decision was going to be made against is old, and the honest next step is a
    fresh reading rather than a decision taken on a stale one.

    Refused on the clock rather than on the stored state. A change is relabelled
    ``expired`` by a sweep, and a deployment whose sweep is not running would
    otherwise leave every lapsed change answerable indefinitely — which is
    exactly what happened here: a remediation proposed at 23:48 with a
    fifteen-minute window was approved at 00:53 and carried out, fifty minutes
    after the reading behind it stopped being current.
    """

    def __init__(self, change_id: str, expired_at: str, now: str) -> None:
        super().__init__(
            f"{change_id!r} could be answered until {expired_at} and it is now {now}. The "
            f"state it was proposed against was read before that window closed, so deciding "
            f"now would be deciding about a cluster nobody has looked at since. Ask for it "
            f"again to get a current reading."
        )
        self.change_id = change_id
        self.expired_at = expired_at


class ChangeAlreadyDecided(ApprovalError):
    """A second decision arrived for a change that already has one.

    The first decision stands. Two reviewers deciding at once is routine, and
    the second one needs to be told what the first decided rather than having
    their click silently discarded.
    """

    def __init__(self, change_id: str, state: str, decided_by: str | None) -> None:
        who = f" by {decided_by!r}" if decided_by else ""
        super().__init__(
            f"{change_id!r} was already {state}{who}. A decision is made once — reload the "
            f"queue to see what was decided."
        )
        self.change_id = change_id
        self.state = state
        self.decided_by = decided_by


# --- Conflicts ---------------------------------------------------------------


class ChangeConflicted(ApprovalError):
    """The target moved between queuing and the decision.

    Names why. "Somebody else changed this field" and "the node was deleted"
    are different situations, and a reviewer re-reviewing the first needs to
    know they are still reviewing something that exists.
    """

    def __init__(self, change_id: str, reason: str, detail: str) -> None:
        super().__init__(
            f"{change_id!r} cannot be approved as it stands: {detail} Re-review it against "
            f"the target's current state."
        )
        self.change_id = change_id
        self.reason = reason
        self.detail = detail


# --- Who may decide ----------------------------------------------------------


class SelfApprovalForbidden(ApprovalError):
    """The requester tried to approve their own change.

    Refused whether they arrived as themselves or through an impersonation. The
    check is against the *real* principal for exactly that reason: a control
    that an admin steps around by impersonating the requester is not one.
    """

    def __init__(self, change_id: str, principal_id: str) -> None:
        super().__init__(
            f"{principal_id!r} requested {change_id!r} and cannot also approve it. This "
            f"organisation's policy forbids self-approval; ask another reviewer."
        )
        self.change_id = change_id
        self.principal_id = principal_id


class ReviewerNotPermitted(ApprovalError):
    """The deciding principal does not hold review permission now.

    Checked at decision time, not only when the change was queued. Somebody
    offboarded between the two is the ordinary case, and a queue-time-only check
    would let their pending authority apply a change days after they left.
    """

    def __init__(self, change_id: str, principal_id: str, node_id: str | None) -> None:
        where = f"at {node_id!r}" if node_id is not None else "in this organisation"
        super().__init__(
            f"{principal_id!r} may no longer review changes {where}, so {change_id!r} cannot "
            f"be decided by them. Permission is re-checked when the decision is made."
        )
        self.change_id = change_id
        self.principal_id = principal_id
        self.node_id = node_id


# --- Security policy ---------------------------------------------------------


class PolicyViolation(ApprovalError):
    """A write broke an organisation-level constraint.

    Carries every violation rather than the first, and never the value. An
    operator fixing a document one field per submission stops using the
    document; a message quoting the value is how a rejected credential reaches
    the log.
    """

    def __init__(self, violations: Sequence[str]) -> None:
        listed = "\n  - ".join(violations)
        super().__init__(
            f"The organisation's security policy refuses this change:\n  - {listed}\n"
            f"Policy constraints bind every role. Change the policy to change the limit."
        )
        self.violations = tuple(violations)


class PolicyLocked(ApprovalError):
    """A descendant tried to set a path the organisation's policy locked.

    Names the policy rather than a node, because this constraint is the
    organisation's and there is no node above it to argue with.
    """

    def __init__(self, path: str) -> None:
        super().__init__(
            f"{path!r} is locked by the organisation's security policy and no node may "
            f"override it. Change the policy, which is itself audited and may be gated."
        )
        self.path = path


__all__ = [
    "ApprovalError",
    "ChangeAlreadyDecided",
    "ChangeExpired",
    "ChangeConflicted",
    "ChangeNotFound",
    "IllegalTransition",
    "PolicyLocked",
    "PolicyViolation",
    "ReviewerNotPermitted",
    "SelfApprovalForbidden",
]
