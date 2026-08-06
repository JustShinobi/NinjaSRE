"""Whether a run is waiting on somebody, in the form a listing can show.

A console listing twenty running investigations is read to answer one question:
which of these needs me. A run that is working and a run that has been stopped
for eleven minutes waiting for somebody to tap a button look identical in a
status column, and the second one is the only one worth opening.

So attention is derived rather than stored — from the interactions that are
open right now, at the moment the listing is built. A stored flag would be a
second copy of a fact the registry already holds, and the copy that drifts is
always the one saying a run needs attention after somebody answered it.

``waiting_since`` is the oldest open interaction rather than the newest. Sorting
a queue by how long it has been ignored is what stops the question nobody
noticed from being the one that stays unanswered.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from core.agent.interaction.models import AttentionState, Interaction, InteractionKind
from core.agent.interaction.registry import InteractionRegistry

#: The metadata key a run record carries its attention state under, so a history
#: listing and a console read the same spelling.
RUN_ATTENTION_KEY = "attention"
RUN_ATTENTION_SINCE_KEY = "attention_since"


@dataclass(frozen=True, slots=True)
class Attention:
    """What a run listing shows about one run's need for a human.

    Counts as well as a state, because "waiting on three approvals" and
    "waiting on one" are the same colour and different amounts of work, and an
    operator triaging a queue is deciding where to spend twenty minutes.
    """

    state: AttentionState = AttentionState.NONE
    questions: int = 0
    approvals: int = 0
    waiting_since: datetime | None = None
    summary: str = ""

    @property
    def needs_attention(self) -> bool:
        """Return whether somebody has to act for this run to continue."""
        return self.state.needs_attention

    def waiting_for(self, now: datetime) -> timedelta:
        """Return how long this run has been blocked, or zero if it is not."""
        if self.waiting_since is None:
            return timedelta()
        return now - self.waiting_since

    def to_metadata(self) -> dict[str, str]:
        """Return the run-record metadata this attention state contributes.

        Strings, because run metadata is a string map and a listing that had to
        coerce types would be a listing where one filter silently matched
        nothing.
        """
        metadata = {RUN_ATTENTION_KEY: self.state.value}
        if self.waiting_since is not None:
            metadata[RUN_ATTENTION_SINCE_KEY] = self.waiting_since.isoformat()
        return metadata


def attention_over(interactions: tuple[Interaction, ...]) -> Attention:
    """Return the attention state ``interactions`` imply.

    Takes the open interactions rather than a registry so a caller holding them
    from anywhere — a restored session, an approvals queue, a listing assembled
    across several runs — gets the same answer as the runtime does.
    """
    open_ones = tuple(held for held in interactions if held.is_open)
    if not open_ones:
        return Attention()

    questions = sum(1 for held in open_ones if held.kind is InteractionKind.QUESTION)
    approvals = sum(1 for held in open_ones if held.kind is InteractionKind.APPROVAL)
    oldest = min(open_ones, key=lambda held: held.raised_at)

    return Attention(
        state=_state_for(questions, approvals),
        questions=questions,
        approvals=approvals,
        waiting_since=oldest.raised_at,
        summary=oldest.describe(),
    )


def attention_of(registry: InteractionRegistry) -> Attention:
    """Return the attention state of the run ``registry`` belongs to."""
    return attention_over(registry.pending)


def _state_for(questions: int, approvals: int) -> AttentionState:
    """Return the state a count of each kind produces."""
    if questions and approvals:
        return AttentionState.WAITING_ON_BOTH
    if approvals:
        return AttentionState.WAITING_ON_APPROVAL
    if questions:
        return AttentionState.WAITING_ON_QUESTION
    return AttentionState.NONE


__all__ = [
    "RUN_ATTENTION_KEY",
    "RUN_ATTENTION_SINCE_KEY",
    "Attention",
    "attention_of",
    "attention_over",
]
