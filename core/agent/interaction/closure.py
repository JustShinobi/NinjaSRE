"""One decision, published once, closing the interaction everywhere it was shown.

The failure this exists to prevent is mundane and constant. A question goes to
the incident's Slack thread, to Discord, and to the console. Somebody answers it
in the console. The two chat messages sit there for the rest of the week with
live buttons on them, and the next person to walk past taps one — getting either
an error they cannot interpret, or, much worse, a second answer to a question
that has already changed what the agent did.

So there is one event and every surface subscribes to it, rather than
per-surface state each surface keeps in step with the others.

**Publishing is idempotent.** One interaction publishes exactly once, tracked by
identifier, because a retried closure must not put a second "answered" message
in a channel that already has one.

**A subscriber that fails does not stop the others.** Closing on three surfaces
is three independent obligations, and the one that raised must not leave the
other two showing a live button.

**The propagation budget is measured and reported, not enforced.** Nothing is
cancelled when a surface is slow; the result says so instead, because "the
console took nine seconds and may still be showing a button" is a fact an
operator can act on and a cancelled delivery is a surface that never closed at
all.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from config.constants.investigation import INTERACTION_CLOSURE_BUDGET_SECONDS
from core.agent.interaction.models import Interaction, InteractionKind, InteractionState
from platform.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class InteractionEvent:
    """What every surface is told when an interaction stops waiting.

    Covers expiry and supersession as well as an answer. A question that lapsed
    is one a surface has to stop showing a button for just as much as one that
    was answered, and a surface subscribing only to answers would leave exactly
    the stalest questions live.
    """

    interaction_id: str
    run_id: str
    kind: InteractionKind
    state: InteractionState
    closed_at: datetime
    summary: str = ""
    answered_by: str = ""
    answer_text: str = ""
    surfaces: tuple[str, ...] = ()

    @classmethod
    def of(cls, interaction: Interaction, *, at: datetime) -> InteractionEvent:
        """Return the event ``interaction`` reaching its current state produces."""
        answer = interaction.answer
        return cls(
            interaction_id=interaction.interaction_id,
            run_id=interaction.run_id,
            kind=interaction.kind,
            state=interaction.state,
            closed_at=answer.answered_at if answer and answer.answered_at else at,
            summary=interaction.describe(),
            answered_by=answer.principal if answer else "",
            answer_text=answer.text if answer else "",
            surfaces=interaction.surfaces,
        )

    @property
    def closes_the_interaction(self) -> bool:
        """Return whether surfaces should stop offering to answer this."""
        return self.state.is_closed

    def to_record(self) -> dict[str, Any]:
        """Return the stored form a transport serialises."""
        return {
            "interaction_id": self.interaction_id,
            "run_id": self.run_id,
            "kind": self.kind.value,
            "state": self.state.value,
            "closed_at": self.closed_at.isoformat(),
            "summary": self.summary,
            "answered_by": self.answered_by,
            "surfaces": list(self.surfaces),
        }


@runtime_checkable
class InteractionSurface(Protocol):
    """A surface that showed an interaction and has to stop showing it.

    Two methods, and the second is what makes a surface renderable at all. This
    is the contract features 021 and 022 implement: show it, and close it.
    """

    @property
    def name(self) -> str:
        """Return what this surface is called, for the log line when it fails."""

    async def present(self, interaction: Interaction) -> None:
        """Show ``interaction`` to this surface's audience."""

    async def closed(self, event: InteractionEvent) -> None:
        """Stop offering to answer the interaction ``event`` closes."""


@dataclass(frozen=True, slots=True)
class Propagation:
    """Which surfaces were closed, which could not be, and how long it took."""

    interaction_id: str = ""
    closed: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()
    elapsed_seconds: float = 0.0
    budget_seconds: float = INTERACTION_CLOSURE_BUDGET_SECONDS
    duplicate: bool = False

    @property
    def within_budget(self) -> bool:
        """Return whether every surface heard inside the configured budget."""
        return self.elapsed_seconds <= self.budget_seconds

    @property
    def reached_everybody(self) -> bool:
        """Return whether no surface was left showing a live interaction."""
        return not self.failed


@dataclass(slots=True)
class InteractionClosure:
    """Publishes each interaction's closure once, to every surface that asked.

    Holds the subscriber list and the set of identifiers already published, and
    nothing else. In particular it holds no interactions: the registry owns
    those, and a publisher that kept its own copy would be a second answer to
    "is this still open".
    """

    surfaces: list[InteractionSurface] = field(default_factory=list)
    budget_seconds: float = INTERACTION_CLOSURE_BUDGET_SECONDS
    clock: Callable[[], float] = time.monotonic
    _published: set[str] = field(default_factory=set, init=False, repr=False)

    def subscribe(self, surface: InteractionSurface) -> InteractionClosure:
        """Register ``surface``, and return this publisher so calls chain."""
        self.surfaces.append(surface)
        return self

    async def present(self, interaction: Interaction) -> tuple[str, ...]:
        """Show ``interaction`` on every surface it names, and return which heard.

        A surface not named on the interaction is not told. Article X: an
        interaction travels only to the operator's configured surfaces, and a
        publisher that fanned out to everybody attached would put an incident's
        question in a channel nobody chose to route it to.
        """
        shown: list[str] = []
        for surface in self._addressed(interaction.surfaces):
            try:
                await surface.present(interaction)
            except Exception as failure:  # noqa: BLE001 — one surface must not stop the rest
                logger.error(
                    "agent.interaction_not_presented",
                    interaction_id=interaction.interaction_id,
                    surface=surface.name,
                    error=str(failure),
                )
            else:
                shown.append(surface.name)
        return tuple(shown)

    async def publish(self, event: InteractionEvent) -> Propagation:
        """Tell every surface, once, and return what that cost.

        A repeat for an interaction already published is dropped and logged
        rather than raised: the caller retrying a closure path has not done
        anything wrong, and the thing that must not happen is a second
        announcement.
        """
        if event.interaction_id in self._published:
            logger.info(
                "agent.interaction_closure_already_published",
                interaction_id=event.interaction_id,
                state=event.state.value,
            )
            return Propagation(
                interaction_id=event.interaction_id,
                budget_seconds=self.budget_seconds,
                duplicate=True,
            )

        self._published.add(event.interaction_id)
        started = self.clock()
        closed: list[str] = []
        failed: list[str] = []
        for surface in self._addressed(event.surfaces):
            try:
                await surface.closed(event)
            except Exception as failure:  # noqa: BLE001 — one surface must not stop the rest
                failed.append(surface.name)
                logger.error(
                    "agent.interaction_closure_failed",
                    interaction_id=event.interaction_id,
                    surface=surface.name,
                    error=str(failure),
                )
            else:
                closed.append(surface.name)

        propagation = Propagation(
            interaction_id=event.interaction_id,
            closed=tuple(closed),
            failed=tuple(failed),
            elapsed_seconds=self.clock() - started,
            budget_seconds=self.budget_seconds,
        )
        if not propagation.within_budget:
            logger.warning(
                "agent.interaction_closure_slow",
                interaction_id=event.interaction_id,
                elapsed_seconds=propagation.elapsed_seconds,
                budget_seconds=self.budget_seconds,
            )
        return propagation

    async def publish_all(
        self, interactions: Sequence[Interaction], *, at: datetime
    ) -> tuple[Propagation, ...]:
        """Publish a batch, which is what an expiry sweep produces."""
        return tuple(
            [await self.publish(InteractionEvent.of(closed, at=at)) for closed in interactions]
        )

    def has_published(self, interaction_id: str) -> bool:
        """Return whether a closure for ``interaction_id`` has already gone out."""
        return interaction_id in self._published

    def _addressed(self, names: Sequence[str]) -> tuple[InteractionSurface, ...]:
        """Return the registered surfaces ``names`` refers to, in registration order.

        An unregistered name is skipped rather than raised on. A run whose
        origin surface has gone away — the channel was archived, the CLI exited
        — still has to close everywhere else, and refusing the whole
        propagation because one addressee is unknown is how the other two keep
        their buttons.
        """
        wanted = set(names)
        return tuple(surface for surface in self.surfaces if surface.name in wanted)


__all__ = [
    "InteractionClosure",
    "InteractionEvent",
    "InteractionSurface",
    "Propagation",
]
