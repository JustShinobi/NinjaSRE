"""A queued change, as the thing the run is waiting on a human for.

A pending change and a question the agent asked are the same situation, and
this module is the one line of code that says so: it turns a ``PendingChange``
into an ``ApprovalInteraction``, and everything the interaction layer already
does then applies to approvals without being written a second time.

What approvals inherit by being converted here:

- **cross-surface closure**, published once, closing every surface that showed
  the change rather than only the one it was decided on;
- **persistence**, so a change still waiting when the process restarts comes
  back answerable or clearly expired;
- **concurrency resolution**, so two reviewers deciding at the same moment
  resolve to one and the second is told who;
- **attention state**, so a run blocked on an approval is distinguishable in a
  listing from one that is working.

**The change stays the source of truth for the decision.** This does not move
approval state into the interaction layer, and it must not: whether something is
approved, what it was approved against, and whether a rollback plan exists are
the approvals service's, and it enforces Article III's "and". The interaction is
the *waiting* half — who is being waited on, where, until when — and the
conversion is one-way for exactly that reason.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from core.agent.interaction.closure import InteractionEvent
from core.agent.interaction.models import (
    NO_SURFACE,
    Answer,
    ApprovalInteraction,
    InteractionState,
)
from platform.approvals.models import ChangeState, PendingChange

#: How a change's state maps onto an interaction's. Both open states become
#: ``PENDING``, because the interaction layer's vocabulary is "somebody is still
#: being waited on" and a conflicted change is somebody being waited on — they
#: just have to answer it against the target's current state.
_INTERACTION_STATES: dict[ChangeState, InteractionState] = {
    ChangeState.PENDING: InteractionState.PENDING,
    ChangeState.CONFLICTED: InteractionState.PENDING,
    ChangeState.APPROVED: InteractionState.ANSWERED,
    ChangeState.REJECTED: InteractionState.ANSWERED,
    ChangeState.EXPIRED: InteractionState.EXPIRED,
}


def interaction_of(
    change: PendingChange,
    *,
    surfaces: Sequence[str] = (),
    blast_radius: str = "",
    rollback_plan: str = "",
    diff: str = "",
) -> ApprovalInteraction:
    """Return ``change`` as the interaction a run is suspended on.

    ``run_id`` is the change's own identifier rather than the investigation's.
    Four of the five change types are not raised by a run at all — a
    configuration edit made in the console has no investigation behind it — and
    an interaction keyed on a run that does not exist would put those changes in
    nobody's attention state. A remediation carries its run in the payload, and
    the caller that has it passes it.
    """
    return ApprovalInteraction(
        interaction_id=change.change_id,
        run_id=change.change_id,
        raised_at=change.created_at,
        expires_at=change.expires_at,
        state=_INTERACTION_STATES[change.state],
        surfaces=tuple(surfaces) or (NO_SURFACE,),
        summary=change.summary(),
        answer=_answer_of(change),
        action=f"{change.change_type.value} change to {change.target}",
        diff=diff,
        blast_radius=blast_radius,
        rollback_plan=rollback_plan,
    )


def event_of(
    change: PendingChange, *, at: datetime, surfaces: Sequence[str] = ()
) -> InteractionEvent:
    """Return the closure event ``change`` reaching its current state produces."""
    return InteractionEvent.of(interaction_of(change, surfaces=surfaces), at=at)


def _answer_of(change: PendingChange) -> Answer | None:
    """Return the decision as the answer that closed the interaction.

    A rejection is an *answer*, not a failure to answer. Surfaces have to stop
    showing a button for a rejected change exactly as much as for an approved
    one, and a mapping that treated "no" as "nobody replied" would leave the
    rejected changes live and the approved ones closed.
    """
    decision = change.decision
    if decision is None:
        return None
    return Answer(
        text="approved"
        if decision.approved
        else f"rejected: {decision.reason or 'no reason given'}",
        principal=decision.decided_by,
        answered_at=decision.decided_at,
        selected_option="approve" if decision.approved else "reject",
    )


__all__ = ["event_of", "interaction_of"]
