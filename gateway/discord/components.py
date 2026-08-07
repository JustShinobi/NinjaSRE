"""Application commands and message components.

Discord's message text limit is the tightest of the four at two thousand
characters, so an approval's four fields are laid out to survive it: labelled
lines rather than an embed, and a diff that is cut before the message is.

**A decided message keeps its text and loses its components.** Discord has a
disabled state for a button, and it is deliberately not used: a greyed-out
button still reads as a control, and the person who lost the race needs a
sentence rather than a shape.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from core.agent.interaction.closure import InteractionEvent
from core.agent.interaction.models import (
    ApprovalInteraction,
    Interaction,
    InteractionKind,
    InteractionState,
    Question,
)
from gateway.chat.commands import COMMAND_CATALOGUE, registration_for
from gateway.chat.port import InteractiveElement
from gateway.discord.client import ACTION_ROW, BUTTON
from gateway.discord.events import custom_id

APPROVAL_CHOICES: tuple[str, ...] = ("approve", "decline")

#: How much of a diff goes into a message. Discord's whole-message ceiling is
#: two thousand characters and the four fields need the rest.
MAX_DIFF_CHARS: Final = 600

#: Buttons per action row, and rows per message, as Discord enforces them.
BUTTONS_PER_ROW: Final = 5

#: Button styles: primary for the affirmative, secondary for everything else.
STYLE_PRIMARY: Final = 1
STYLE_SECONDARY: Final = 2


def render(interaction: Interaction) -> InteractiveElement:
    """Return the message and components ``interaction`` is decided with."""
    if isinstance(interaction, ApprovalInteraction):
        return _approval(interaction)
    if isinstance(interaction, Question):
        return _question(interaction)
    return InteractiveElement(
        interaction_id=interaction.interaction_id,
        kind=interaction.kind.value,
        fallback_text=interaction.describe(),
        payload={"components": []},
    )


def _approval(approval: ApprovalInteraction) -> InteractiveElement:
    """Return the approval message: four fields, the diff, and two buttons."""
    lines = [
        f"**Approval needed** — {approval.describe()}",
        f"**Target:** {approval.action}",
        f"**Blast radius:** {approval.blast_radius or '—'}",
        f"**Rollback plan:** {approval.rollback_plan or '—'}",
    ]
    if approval.diff:
        lines.append(f"```diff\n{approval.diff[:MAX_DIFF_CHARS]}\n```")

    return InteractiveElement(
        interaction_id=approval.interaction_id,
        kind=InteractionKind.APPROVAL.value,
        fallback_text="\n".join(lines),
        payload={"components": buttons(approval.interaction_id, APPROVAL_CHOICES)},
        choices=APPROVAL_CHOICES,
    )


def _question(question: Question) -> InteractiveElement:
    """Return the question message, with a button per option."""
    lines = [f"**Question** — {question.text}"]
    if question.reason:
        lines.append(f"**Why it matters:** {question.reason}")

    return InteractiveElement(
        interaction_id=question.interaction_id,
        kind=InteractionKind.QUESTION.value,
        fallback_text="\n".join(lines),
        payload={"components": buttons(question.interaction_id, question.options)},
        choices=tuple(question.options),
    )


def buttons(interaction_id: str, choices: Sequence[str]) -> list[Mapping[str, Any]]:
    """Return the action rows offering ``choices`` for ``interaction_id``."""
    made = [
        {
            "type": BUTTON,
            "custom_id": custom_id(interaction_id, choice),
            "label": choice,
            "style": STYLE_PRIMARY if choice in {"approve", "yes"} else STYLE_SECONDARY,
        }
        for choice in choices
    ]
    return [
        {"type": ACTION_ROW, "components": made[index : index + BUTTONS_PER_ROW]}
        for index in range(0, len(made), BUTTONS_PER_ROW)
    ]


def outcome_text(event: InteractionEvent) -> str:
    """Return the sentence a closed interaction shows."""
    if event.state is InteractionState.ANSWERED:
        who = event.answered_by or "somebody"
        return f"**{event.summary}**\nDecided by {who}: **{event.answer_text or 'answered'}**"
    if event.state is InteractionState.EXPIRED:
        return (
            f"**{event.summary}**\nExpired without a decision. Nothing was done; "
            f"ask again if it still applies."
        )
    return f"**{event.summary}**\nClosed ({event.state.value})."


def application_commands() -> tuple[Mapping[str, Any], ...]:
    """Return the shared catalogue as Discord application commands.

    Generated rather than declared, so a command added to the catalogue is
    registered here without anybody remembering to.
    """
    registered = registration_for("discord")
    if len(registered) != len(COMMAND_CATALOGUE):
        raise ValueError(
            f"the catalogue has {len(COMMAND_CATALOGUE)} commands and the renderer produced "
            f"{len(registered)}. One of them has stopped being generated from the other."
        )
    return registered


__all__ = [
    "APPROVAL_CHOICES",
    "BUTTONS_PER_ROW",
    "MAX_DIFF_CHARS",
    "STYLE_PRIMARY",
    "STYLE_SECONDARY",
    "application_commands",
    "buttons",
    "outcome_text",
    "render",
]
