"""Adaptive Cards for reports, approvals, and questions.

A card is what makes Teams worth adapting rather than posting plain text into:
the four fields of an approval render as a fact set, the diff renders as
monospace, and the decision is two buttons rather than a sentence somebody has
to type correctly.

**Every action carries the interaction id.** Teams routes a card submission back
by activity, not by control, so the identifier has to be in the payload or the
decision arrives with nothing to attach it to.

**A decided card keeps its facts and loses its buttons.** Replacing the whole
card would delete the record of what was decided about; disabling the buttons
would leave controls that look pressable. Keeping the body and dropping the
actions is the only option that leaves the thread readable afterwards.
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

#: The card schema Teams renders. Pinned rather than tracking the newest: a
#: client on an older version silently drops elements it does not know, and the
#: element it drops is usually the one carrying the decision.
CARD_SCHEMA: Final = "http://adaptivecards.io/schemas/adaptive-card.json"
CARD_VERSION: Final = "1.5"
CARD_CONTENT_TYPE: Final = "application/vnd.microsoft.card.adaptive"

APPROVAL_CHOICES: tuple[str, ...] = ("approve", "decline")

#: How much of a diff a card carries. A card past roughly this stops rendering
#: on mobile, which is where approvals are actually decided.
MAX_DIFF_CHARS: Final = 1_200


def render(interaction: Interaction) -> InteractiveElement:
    """Return the Adaptive Card ``interaction`` is decided with."""
    if isinstance(interaction, ApprovalInteraction):
        return _approval(interaction)
    if isinstance(interaction, Question):
        return _question(interaction)
    return _element(
        interaction.interaction_id,
        interaction.kind.value,
        interaction.describe(),
        body=[_text(interaction.describe())],
    )


def report_card(title: str, body: str) -> Mapping[str, Any]:
    """Return the card a finished report is delivered as."""
    return _card([_text(title, weight="Bolder", size="Large"), _text(body)])


def _approval(approval: ApprovalInteraction) -> InteractiveElement:
    """Return the approval card: the four fields, the diff, and two buttons."""
    body: list[Mapping[str, Any]] = [
        _text("Approval needed", weight="Bolder", size="Large"),
        _text(approval.describe(), wrap=True),
        _facts(
            ("Target", approval.action),
            ("Blast radius", approval.blast_radius),
            ("Rollback plan", approval.rollback_plan),
        ),
    ]
    if approval.diff:
        body.append(_text(approval.diff[:MAX_DIFF_CHARS], monospace=True))

    fallback = (
        f"Approval needed: {approval.describe()}\n"
        f"Target: {approval.action}\n"
        f"Blast radius: {approval.blast_radius}\n"
        f"Rollback plan: {approval.rollback_plan}"
    )
    return _element(
        approval.interaction_id,
        InteractionKind.APPROVAL.value,
        fallback,
        body=body,
        choices=APPROVAL_CHOICES,
    )


def _question(question: Question) -> InteractiveElement:
    """Return the question card, with a button per option."""
    body: list[Mapping[str, Any]] = [
        _text("Question", weight="Bolder", size="Large"),
        _text(question.text, wrap=True),
    ]
    if question.reason:
        body.append(_text(f"Why it matters: {question.reason}", wrap=True, subtle=True))

    fallback = (
        f"Question: {question.text}\nWhy it matters: {question.reason}"
        if question.reason
        else f"Question: {question.text}"
    )
    return _element(
        question.interaction_id,
        InteractionKind.QUESTION.value,
        fallback,
        body=body,
        choices=tuple(question.options),
    )


def closed_card(event: InteractionEvent) -> tuple[Mapping[str, Any], str]:
    """Return the card and the fallback text a decided element is left showing."""
    text = outcome_text(event)
    return (
        _card([_text(event.summary, weight="Bolder"), _text(text, wrap=True)]),
        text,
    )


def outcome_text(event: InteractionEvent) -> str:
    """Return the sentence a closed interaction shows."""
    if event.state is InteractionState.ANSWERED:
        who = event.answered_by or "somebody"
        return f"Decided by {who}: {event.answer_text or 'answered'}"
    if event.state is InteractionState.EXPIRED:
        return "Expired without a decision. Nothing was done; ask again if it still applies."
    return f"Closed ({event.state.value})."


def _element(
    interaction_id: str,
    kind: str,
    fallback: str,
    *,
    body: Sequence[Mapping[str, Any]],
    choices: tuple[str, ...] = (),
) -> InteractiveElement:
    """Return the interactive element a card plus its buttons makes."""
    return InteractiveElement(
        interaction_id=interaction_id,
        kind=kind,
        fallback_text=fallback,
        payload={"card": _card(body, actions=_actions(interaction_id, choices))},
        choices=choices,
    )


def _card(
    body: Sequence[Mapping[str, Any]], *, actions: Sequence[Mapping[str, Any]] = ()
) -> Mapping[str, Any]:
    card: dict[str, Any] = {
        "$schema": CARD_SCHEMA,
        "type": "AdaptiveCard",
        "version": CARD_VERSION,
        "body": list(body),
    }
    if actions:
        card["actions"] = list(actions)
    return card


def _actions(interaction_id: str, choices: Sequence[str]) -> tuple[Mapping[str, Any], ...]:
    return tuple(
        {
            "type": "Action.Execute",
            "title": choice,
            "verb": "ninjasre.decide",
            "data": {"interaction_id": interaction_id, "choice": choice},
        }
        for choice in choices
    )


def _text(
    text: str,
    *,
    weight: str = "Default",
    size: str = "Default",
    wrap: bool = True,
    subtle: bool = False,
    monospace: bool = False,
) -> Mapping[str, Any]:
    block: dict[str, Any] = {
        "type": "TextBlock",
        "text": text,
        "wrap": wrap,
        "weight": weight,
        "size": size,
    }
    if subtle:
        block["isSubtle"] = True
    if monospace:
        block["fontType"] = "Monospace"
    return block


def _facts(*pairs: tuple[str, str]) -> Mapping[str, Any]:
    return {
        "type": "FactSet",
        "facts": [{"title": label, "value": value or "—"} for label, value in pairs],
    }


def attachment_of(card: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return ``card`` as the attachment an activity carries it in."""
    return {"contentType": CARD_CONTENT_TYPE, "content": dict(card)}


__all__ = [
    "APPROVAL_CHOICES",
    "CARD_CONTENT_TYPE",
    "CARD_SCHEMA",
    "CARD_VERSION",
    "MAX_DIFF_CHARS",
    "attachment_of",
    "closed_card",
    "outcome_text",
    "render",
    "report_card",
]
