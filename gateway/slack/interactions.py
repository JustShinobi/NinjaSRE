"""Approvals and questions as Block Kit, and what is left after a decision.

An approval renders four things because a reviewer deciding from their phone at
three in the morning needs all four and will not go and find any of them: what
would change, the diff, what else it touches, and how it is undone. A card that
showed only "approve this?" is a card people approve without reading, which is
worse than no card.

**A closed element has no buttons left.** ``closed_blocks`` replaces the whole
block list rather than disabling the actions, because a disabled button still
looks like a control and somebody will press it. What remains is a sentence
saying who decided and what they decided — which is also what the person who
lost the race needs to read.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from core.agent.interaction.closure import InteractionEvent
from core.agent.interaction.models import (
    ApprovalInteraction,
    Interaction,
    InteractionKind,
    InteractionState,
    Question,
)
from gateway.chat.port import InteractiveElement
from gateway.slack.events import ACTION_PREFIX

#: What an approval offers. Two words and nothing else — an approval read
#: generously out of a free-text reply is an approval nobody gave.
APPROVAL_CHOICES: tuple[str, ...] = ("approve", "decline")

#: How much of a diff goes in a message. Slack refuses a block over 3,000
#: characters, and a reviewer does not read more than this on a phone anyway.
MAX_DIFF_CHARS = 1_200


def render(interaction: Interaction) -> InteractiveElement:
    """Return the Block Kit control ``interaction`` is decided with."""
    if isinstance(interaction, ApprovalInteraction):
        return _approval(interaction)
    if isinstance(interaction, Question):
        return _question(interaction)
    return InteractiveElement(
        interaction_id=interaction.interaction_id,
        kind=interaction.kind.value,
        fallback_text=interaction.describe(),
        payload={"blocks": [_section(interaction.describe())]},
    )


def _approval(approval: ApprovalInteraction) -> InteractiveElement:
    """Return the four-field approval card and its two buttons."""
    fallback = "\n".join(
        (
            f"*Approval needed:* {approval.describe()}",
            f"*Target:* {approval.action}",
            f"*Blast radius:* {approval.blast_radius}",
            f"*Rollback plan:* {approval.rollback_plan}",
        )
    )
    blocks: list[Mapping[str, Any]] = [
        _section(f"*Approval needed*\n{approval.describe()}"),
        _fields(
            ("Target", approval.action),
            ("Blast radius", approval.blast_radius),
            ("Rollback plan", approval.rollback_plan),
        ),
    ]
    if approval.diff:
        blocks.append(_section(f"```{approval.diff[:MAX_DIFF_CHARS]}```"))
    blocks.append(_actions(approval.interaction_id, APPROVAL_CHOICES))

    return InteractiveElement(
        interaction_id=approval.interaction_id,
        kind=InteractionKind.APPROVAL.value,
        fallback_text=fallback,
        payload={"blocks": blocks},
        choices=APPROVAL_CHOICES,
    )


def _question(question: Question) -> InteractiveElement:
    """Return the question card, with a button per option."""
    fallback = (
        f"*Question:* {question.text}\n*Why it matters:* {question.reason}"
        if question.reason
        else f"*Question:* {question.text}"
    )
    blocks: list[Mapping[str, Any]] = [_section(f"*Question*\n{question.text}")]
    if question.reason:
        blocks.append(_context(f"Why it matters: {question.reason}"))
    if question.options:
        blocks.append(_actions(question.interaction_id, question.options))

    return InteractiveElement(
        interaction_id=question.interaction_id,
        kind=InteractionKind.QUESTION.value,
        fallback_text=fallback,
        payload={"blocks": blocks},
        choices=tuple(question.options),
    )


def closed_blocks(event: InteractionEvent) -> tuple[Sequence[Mapping[str, Any]], str]:
    """Return the blocks and the fallback text a decided element is left showing."""
    text = outcome_text(event)
    return ([_section(text)], text)


def outcome_text(event: InteractionEvent) -> str:
    """Return the sentence a closed interaction shows, in every channel that saw it."""
    if event.state is InteractionState.ANSWERED:
        who = event.answered_by or "somebody"
        decision = event.answer_text or "answered"
        return f"*{event.summary}*\nDecided by {who}: *{decision}*"
    if event.state is InteractionState.EXPIRED:
        return (
            f"*{event.summary}*\nExpired without a decision. Nothing was done; "
            f"ask again if it still applies."
        )
    return f"*{event.summary}*\nClosed ({event.state.value})."


def _section(text: str) -> Mapping[str, Any]:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _context(text: str) -> Mapping[str, Any]:
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": text}]}


def _fields(*pairs: tuple[str, str]) -> Mapping[str, Any]:
    return {
        "type": "section",
        "fields": [
            {"type": "mrkdwn", "text": f"*{label}*\n{value or '—'}"} for label, value in pairs
        ],
    }


def _actions(interaction_id: str, choices: Sequence[str]) -> Mapping[str, Any]:
    """Return one button per choice, each carrying the interaction it decides."""
    return {
        "type": "actions",
        "block_id": f"{ACTION_PREFIX}{interaction_id}",
        "elements": [
            {
                "type": "button",
                "action_id": f"{ACTION_PREFIX}{interaction_id}",
                "text": {"type": "plain_text", "text": choice},
                "value": choice,
                **({"style": "primary"} if choice in {"approve", "yes"} else {}),
            }
            for choice in choices
        ],
    }


__all__ = [
    "APPROVAL_CHOICES",
    "MAX_DIFF_CHARS",
    "closed_blocks",
    "outcome_text",
    "render",
]
