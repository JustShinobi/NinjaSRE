"""The pending interactions of one run, and the only place they change state.

Everything that can close an interaction goes through ``resolve``, ``expire``,
or ``supersede`` here. That is what makes "the first answer wins" a property
rather than a race: the transition is conditional on the interaction still being
open, and the loser gets a value saying who beat them instead of an exception
nobody can render.

The registry is per run and is not shared. Two runs sharing one would let an
answer to a question raised by one investigation close a question raised by
another, which is a bug that would only ever be found in production, during an
alert storm, on the run that mattered.

**Nothing here reaches storage.** ``persistence`` is what writes a registry into
a session and reads it back, and keeping the two apart is what lets the closure
path be tested without a store and the store be tested without a clock.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from core.agent.interaction.models import (
    Answer,
    Interaction,
    InteractionKind,
    InteractionState,
    Resolution,
)
from platform.observability.logging import get_logger

logger = get_logger(__name__)


def _utc_now() -> datetime:
    """Return the current instant, timezone-aware."""
    return datetime.now(UTC)


class UnknownInteraction(KeyError):
    """An interaction identifier nothing was raised under.

    Distinct from "already answered" on purpose. A surface that answered a
    question the run never asked has a wiring problem; one that answered a
    question somebody else answered first has not, and telling an operator the
    same thing in both cases hides the first.
    """

    def __init__(self, interaction_id: str) -> None:
        super().__init__(interaction_id)
        self.interaction_id = interaction_id

    def __str__(self) -> str:
        return f"no interaction {self.interaction_id!r} is pending on this run"


@dataclass(slots=True)
class InteractionRegistry:
    """Every interaction one run has raised, open or closed.

    Closed ones are kept rather than dropped. An answer arriving after the
    investigation concluded still has to be told what happened to the question,
    and a registry that forgot would report it as unknown — which reads as a bug
    to whoever is looking at it, when it is the ordinary shape of an incident.
    """

    run_id: str = ""
    clock: Callable[[], datetime] = _utc_now
    identifiers: Callable[[], str] = lambda: uuid.uuid4().hex[:16]
    _interactions: dict[str, Interaction] = field(default_factory=dict, repr=False)

    # -- raising --------------------------------------------------------------

    def raise_interaction(self, interaction: Interaction) -> Interaction:
        """Store ``interaction`` as pending and return it."""
        if interaction.interaction_id in self._interactions:
            raise ValueError(
                f"{interaction.interaction_id!r} was already raised on this run. Raising it "
                f"again would give two surfaces two identifiers for one question."
            )
        self._interactions[interaction.interaction_id] = interaction
        logger.info(
            "agent.interaction_raised",
            run_id=interaction.run_id,
            interaction_id=interaction.interaction_id,
            kind=interaction.kind.value,
            surfaces=list(interaction.surfaces),
        )
        return interaction

    def next_identifier(self) -> str:
        """Return an identifier for an interaction about to be raised."""
        return self.identifiers()

    # -- reading --------------------------------------------------------------

    def get(self, interaction_id: str) -> Interaction:
        """Return the interaction with ``interaction_id``, or raise naming it."""
        found = self._interactions.get(interaction_id)
        if found is None:
            raise UnknownInteraction(interaction_id)
        return found

    def find(self, interaction_id: str) -> Interaction | None:
        """Return the interaction with ``interaction_id``, or ``None``."""
        return self._interactions.get(interaction_id)

    @property
    def pending(self) -> tuple[Interaction, ...]:
        """Return the open interactions, longest-waiting first."""
        return tuple(
            sorted(
                (held for held in self._interactions.values() if held.is_open),
                key=lambda held: held.raised_at,
            )
        )

    @property
    def all_interactions(self) -> tuple[Interaction, ...]:
        """Return everything raised on this run, oldest first."""
        return tuple(sorted(self._interactions.values(), key=lambda held: held.raised_at))

    def pending_of(self, kind: InteractionKind) -> tuple[Interaction, ...]:
        """Return the open interactions of one kind, longest-waiting first."""
        return tuple(held for held in self.pending if held.kind is kind)

    def __len__(self) -> int:
        return len(self._interactions)

    def __bool__(self) -> bool:
        """Return whether anything is still open."""
        return bool(self.pending)

    # -- closing --------------------------------------------------------------

    def resolve(self, interaction_id: str, answer: Answer) -> Resolution:
        """Close ``interaction_id`` with ``answer``, or report who got there first.

        The conditional transition *is* the concurrency resolution. Two surfaces
        calling this with two answers both find the interaction; exactly one
        finds it open, and the other is handed the answer that won so it can
        tell its human what the question was actually answered with rather than
        only that they were late.
        """
        held = self.get(interaction_id)
        if held.state.is_closed:
            existing = held.answer
            logger.info(
                "agent.interaction_already_closed",
                run_id=held.run_id,
                interaction_id=interaction_id,
                state=held.state.value,
                answered_by=existing.principal if existing else "",
            )
            return Resolution(
                interaction=held,
                won=False,
                answered_by=existing.principal if existing else "",
                reason=_already_closed_reason(held),
            )

        answered = answer if answer.answered_at is not None else _stamp(answer, self.clock())
        closed = held.answered_with(answered)
        self._interactions[interaction_id] = closed
        logger.info(
            "agent.interaction_answered",
            run_id=closed.run_id,
            interaction_id=interaction_id,
            kind=closed.kind.value,
            principal=answered.principal,
            surface=answered.surface,
        )
        return Resolution(interaction=closed, won=True)

    def expire_due(self, now: datetime | None = None) -> tuple[Interaction, ...]:
        """Close every interaction whose window has passed, and return them."""
        at = now if now is not None else self.clock()
        lapsed: list[Interaction] = []
        for interaction_id, held in list(self._interactions.items()):
            if not held.has_expired(at):
                continue
            closed = held.expired()
            self._interactions[interaction_id] = closed
            lapsed.append(closed)
            logger.info(
                "agent.interaction_expired",
                run_id=closed.run_id,
                interaction_id=interaction_id,
                kind=closed.kind.value,
            )
        return tuple(lapsed)

    def supersede_open(self, reason: str = "") -> tuple[Interaction, ...]:
        """Close everything still open because it stopped applying, and return them.

        What a concluded run, a cancellation, and a human takeover all do. An
        investigation that finished with a question still live leaves a button
        somebody will press, and pressing it would answer a run that is gone.
        """
        closed: list[Interaction] = []
        for interaction_id, held in list(self._interactions.items()):
            if not held.is_open:
                continue
            superseded = held.superseded()
            self._interactions[interaction_id] = superseded
            closed.append(superseded)
        if closed:
            logger.info(
                "agent.interactions_superseded",
                run_id=self.run_id,
                count=len(closed),
                reason=reason,
            )
        return tuple(closed)

    # -- restoring ------------------------------------------------------------

    def restore(self, interactions: Iterable[Interaction]) -> None:
        """Replace this registry's contents with ``interactions``.

        Used by resumption. Replaces rather than merges, because a registry
        being restored is one that holds nothing worth keeping, and merging
        would silently prefer whichever copy happened to be there.
        """
        self._interactions = {held.interaction_id: held for held in interactions}


def _stamp(answer: Answer, at: datetime) -> Answer:
    """Return ``answer`` carrying the instant it was recorded."""
    return replace(answer, answered_at=at)


def _already_closed_reason(interaction: Interaction) -> str:
    """Return what the losing surface tells its human."""
    match interaction.state:
        case InteractionState.ANSWERED:
            who = interaction.answer.principal if interaction.answer else "somebody else"
            return f"this was already answered by {who or 'somebody else'}"
        case InteractionState.EXPIRED:
            return "this expired before it was answered, and the run continued without it"
        case _:
            return "this no longer applies: the run it belongs to has moved on"


__all__ = [
    "InteractionRegistry",
    "UnknownInteraction",
]
