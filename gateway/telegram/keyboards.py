"""Inline keyboards for approvals and questions.

Telegram has no rich card, so the four fields of an approval are the message
text and the decision is a row of buttons under it. That constrains the layout
in a way the other platforms are not: the text has to be readable as plain text,
because that is all it is.

**A decided keyboard is removed, not disabled.** Telegram has no disabled state,
and a button that still exists is a button somebody presses. The message is
rewritten with an empty keyboard and a sentence saying who decided what.
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
from gateway.chat.port import InteractiveElement
from gateway.telegram.events import callback_data

APPROVAL_CHOICES: tuple[str, ...] = ("approve", "decline")

#: How much of a diff goes into the message. Telegram's own ceiling is 4,096
#: characters for the whole message, and the four fields need room around it.
MAX_DIFF_CHARS: Final = 900

#: Buttons per row. Two decisions side by side; more than that wraps badly on a
#: phone, which is where these are pressed.
BUTTONS_PER_ROW: Final = 2

#: The keyboard a closed message is left with — empty, and sent explicitly so
#: Telegram replaces the old one rather than keeping it.
EMPTY_KEYBOARD: Mapping[str, Any] = {"inline_keyboard": []}


def render(interaction: Interaction) -> InteractiveElement:
    """Return the message and keyboard ``interaction`` is decided with."""
    if isinstance(interaction, ApprovalInteraction):
        return _approval(interaction)
    if isinstance(interaction, Question):
        return _question(interaction)
    return InteractiveElement(
        interaction_id=interaction.interaction_id,
        kind=interaction.kind.value,
        fallback_text=interaction.describe(),
        payload={"reply_markup": EMPTY_KEYBOARD},
    )


def _approval(approval: ApprovalInteraction) -> InteractiveElement:
    """Return the approval message: four fields, the diff, and two buttons."""
    lines = [
        f"Approval needed: {approval.describe()}",
        "",
        f"Target: {approval.action}",
        f"Blast radius: {approval.blast_radius or '—'}",
        f"Rollback plan: {approval.rollback_plan or '—'}",
    ]
    if approval.diff:
        lines.extend(("", approval.diff[:MAX_DIFF_CHARS]))

    return InteractiveElement(
        interaction_id=approval.interaction_id,
        kind=InteractionKind.APPROVAL.value,
        fallback_text="\n".join(lines),
        payload={"reply_markup": keyboard(approval.interaction_id, APPROVAL_CHOICES)},
        choices=APPROVAL_CHOICES,
    )


def _question(question: Question) -> InteractiveElement:
    """Return the question message, with a button per option."""
    lines = [f"Question: {question.text}"]
    if question.reason:
        lines.extend(("", f"Why it matters: {question.reason}"))

    return InteractiveElement(
        interaction_id=question.interaction_id,
        kind=InteractionKind.QUESTION.value,
        fallback_text="\n".join(lines),
        payload={"reply_markup": keyboard(question.interaction_id, question.options)},
        choices=tuple(question.options),
    )


def keyboard(interaction_id: str, choices: Sequence[str]) -> Mapping[str, Any]:
    """Return the inline keyboard offering ``choices`` for ``interaction_id``."""
    buttons = [
        {"text": choice, "callback_data": callback_data(interaction_id, choice)}
        for choice in choices
    ]
    rows = [
        buttons[index : index + BUTTONS_PER_ROW]
        for index in range(0, len(buttons), BUTTONS_PER_ROW)
    ]
    return {"inline_keyboard": rows}


def outcome_text(event: InteractionEvent) -> str:
    """Return the sentence a closed interaction shows."""
    if event.state is InteractionState.ANSWERED:
        who = event.answered_by or "somebody"
        return f"{event.summary}\nDecided by {who}: {event.answer_text or 'answered'}"
    if event.state is InteractionState.EXPIRED:
        return (
            f"{event.summary}\nExpired without a decision. Nothing was done; "
            f"ask again if it still applies."
        )
    return f"{event.summary}\nClosed ({event.state.value})."


__all__ = [
    "APPROVAL_CHOICES",
    "BUTTONS_PER_ROW",
    "EMPTY_KEYBOARD",
    "MAX_DIFF_CHARS",
    "keyboard",
    "outcome_text",
    "render",
]
