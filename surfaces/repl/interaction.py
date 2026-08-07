"""A question or an approval, answered where the person already is.

Article III, clause 2: an approval prompt appears at the surface the human is
already using, and never sends them somewhere else to say yes. During an
incident, "open the console and approve it" is a context switch that costs more
than the change is usually worth, and the surface that made them leave is the
one they stop using.

Both kinds go through one path because ``core.agent.interaction`` already says
they are the same situation. What differs is what a reviewer is shown before
they answer: a question shows its reason and its options, an approval shows the
diff, the blast radius, and the rollback plan — and it shows all three, because
an approval granted without seeing the rollback plan is an approval of
something nobody has established is reversible.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import IO

from config.constants.surfaces import SURFACE_REPL
from core.agent.interaction.models import (
    Answer,
    ApprovalInteraction,
    Interaction,
    InteractionKind,
    Question,
    Resolution,
)
from core.agent.interaction.registry import InteractionRegistry, UnknownInteraction
from platform.observability.logging import get_logger
from surfaces.cli.errors import NotFoundError
from surfaces.cli.output.degradation import PLAIN, Terminal
from surfaces.cli.output.tables import Detail, bullet_list
from surfaces.repl.session import ReplSession

logger = get_logger(__name__)

#: What an approval answered with means. Anything else is refused rather than
#: guessed at: an approval is the one place where reading an ambiguous answer
#: generously would apply a production change nobody agreed to.
APPROVE = "approve"
DECLINE = "decline"
APPROVAL_ANSWERS = (APPROVE, DECLINE)


def render_question(question: Question, terminal: Terminal = PLAIN) -> str:
    """Return what somebody is shown before answering a question.

    The reason is not decoration. Whoever is reading this did not follow the
    investigation, and "what changes depending on your answer" is the
    difference between a question that gets answered and one that gets scrolled
    past.
    """
    blocks = [
        Detail(
            title=f"{terminal.glyph('warning')} the run is waiting on you",
            pairs=(
                ("Question", question.text),
                ("Why", question.reason or "not stated"),
                ("Expires", question.expires_at.isoformat()),
            ),
        ).render(terminal)
    ]
    if question.options:
        blocks.extend(("", "Options", bullet_list(list(question.options), terminal=terminal)))
    blocks.extend(("", f"Answer with: /answer {question.interaction_id} <your answer>"))
    return "\n".join(blocks)


def render_approval(approval: ApprovalInteraction, terminal: Terminal = PLAIN) -> str:
    """Return what a reviewer is shown before approving a change.

    Everything, every time. A renderer that abbreviated the diff for a change it
    judged small would be making the judgement the reviewer is there to make.
    """
    head = Detail(
        title=f"{terminal.glyph('warning')} a change needs your approval",
        pairs=(
            ("Action", approval.action),
            ("Blast radius", approval.blast_radius or "not stated"),
            ("Expires", approval.expires_at.isoformat()),
        ),
        sections=(
            ("Change", approval.diff),
            ("Rollback plan", approval.rollback_plan or "none recorded — this is not reversible"),
        ),
    ).render(terminal)
    return f"{head}\n\nApprove with: /approve {approval.interaction_id} approve|decline"


def render(interaction: Interaction, terminal: Terminal = PLAIN) -> str:
    """Return what somebody is shown for whichever kind this is."""
    if isinstance(interaction, ApprovalInteraction):
        return render_approval(interaction, terminal)
    if isinstance(interaction, Question):
        return render_question(interaction, terminal)
    return Detail(
        title=f"{terminal.glyph('warning')} {interaction.describe()}",
        pairs=(("Expires", interaction.expires_at.isoformat()),),
    ).render(terminal)


@dataclass(slots=True)
class InlineInteractions:
    """What the REPL does with everything a run is waiting on.

    Holds the registry rather than a copy of the pending set. Two surfaces may
    be answering the same question, and the registry's conditional transition
    *is* the concurrency resolution — reading it into a local list here would
    reintroduce the race it exists to remove.
    """

    registry: InteractionRegistry
    out: IO[str]
    session: ReplSession
    principal_id: str = ""
    terminal: Terminal = PLAIN

    def pending(self, kind: InteractionKind | None = None) -> tuple[Interaction, ...]:
        """Return what is open, longest-waiting first."""
        return self.registry.pending_of(kind) if kind else self.registry.pending

    def show(self, interaction: Interaction) -> None:
        """Present one interaction inline."""
        self.out.write(render(interaction, self.terminal) + "\n")
        self.session.awaiting = tuple(
            dict.fromkeys((*self.session.awaiting, interaction.interaction_id))
        )

    def show_pending(self, kind: InteractionKind | None = None) -> int:
        """Present everything open of ``kind`` and return how many there were."""
        open_now = self.pending(kind)
        for interaction in open_now:
            self.show(interaction)
        if not open_now:
            self.out.write("nothing is waiting on you\n")
        return len(open_now)

    def _resolve(self, interaction_id: str, text: str, *, option: str = "") -> Resolution:
        """Close one interaction and report what happened to it.

        Raises:
            NotFoundError: nothing was raised under that identifier.
        """
        try:
            resolution = self.registry.resolve(
                interaction_id,
                Answer(
                    text=text,
                    principal=self.principal_id,
                    selected_option=option,
                    surface=SURFACE_REPL,
                ),
            )
        except UnknownInteraction as unknown:
            raise NotFoundError(str(unknown), remedy="see what is open with /status") from unknown

        self.session.awaiting = tuple(
            found for found in self.session.awaiting if found != interaction_id
        )
        logger.info(
            "repl.interaction_answered",
            interaction_id=interaction_id,
            won=resolution.won,
            kind=resolution.interaction.kind.value,
        )
        return resolution

    def answer(self, interaction_id: str, text: str) -> Resolution:
        """Answer a pending question.

        Raises:
            NotFoundError: nothing was raised under that identifier.
        """
        resolution = self._resolve(interaction_id, text)
        self.out.write(self._outcome_line(resolution) + "\n")
        return resolution

    def approve(self, interaction_id: str, decision: str) -> Resolution:
        """Approve or decline a pending change.

        Refuses anything that is not one of the two words. An approval read
        generously out of "yeah probably" is an approval nobody gave.

        Raises:
            NotFoundError: nothing was raised under that identifier.
            ValueError: the decision was not ``approve`` or ``decline``.
        """
        choice = decision.strip().lower()
        if choice not in APPROVAL_ANSWERS:
            raise ValueError(
                f"{decision!r} is not a decision. Say {' or '.join(APPROVAL_ANSWERS)} — "
                f"an approval is not a thing to infer from a sentence."
            )
        resolution = self._resolve(interaction_id, choice, option=choice)
        self.out.write(self._outcome_line(resolution) + "\n")
        return resolution

    def takeover(self, reason: str = "") -> tuple[Interaction, ...]:
        """Close everything open because the human is driving now.

        An investigation somebody has taken over must not leave a live question
        behind. Pressing the button on one would answer a run that has stopped
        listening, which is worse than no button at all.
        """
        closed = self.registry.supersede_open(reason or "a human took over")
        self.session.awaiting = ()
        for interaction in closed:
            self.out.write(f"closed: {interaction.describe()}\n")
        return closed

    def _outcome_line(self, resolution: Resolution) -> str:
        """Return the line the answering surface shows for a resolution."""
        if resolution.won:
            return f"{self.terminal.glyph('ok')} answered"
        who = resolution.answered_by or "somebody else"
        return f"{self.terminal.glyph('warning')} too late: {resolution.reason} ({who})"


def only_one(pending: Sequence[Interaction]) -> Interaction | None:
    """Return the single pending interaction, or ``None`` when it is not single.

    What lets ``/approve`` with no identifier work when there is exactly one
    thing waiting, and refuse when there are two. Guessing which of two
    production changes somebody meant is not a convenience.
    """
    return pending[0] if len(pending) == 1 else None


__all__ = [
    "APPROVAL_ANSWERS",
    "APPROVE",
    "DECLINE",
    "InlineInteractions",
    "only_one",
    "render",
    "render_approval",
    "render_question",
]
