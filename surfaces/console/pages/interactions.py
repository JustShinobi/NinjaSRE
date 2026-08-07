"""What is waiting on a person: questions to answer, changes to approve.

The approval card is the most consequential thing this console renders. FR-009
lists what has to be on it — target, current state, proposed change, blast
radius, rollback plan, motivating evidence — and every one of those is a section
that is rendered whether or not the data is there, saying so when it is not.

That last part is the design decision. An approval card that omitted "rollback
plan" when there was none would look identical to one where nobody scrolled far
enough, and the reviewer would approve a change with no undo without ever being
told. Absence has to be stated.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from surfaces.console.html import Child, Element, element
from surfaces.console.pages.shell import (
    PageContext,
    card,
    definitions,
    form,
    form_field,
    heading,
    value_or_dash,
)
from surfaces.console.permissions import Action, action_control

#: What ``kind`` an interaction carries when it is a change awaiting approval.
APPROVAL_KIND = "approval"


def interaction_queue_body(
    context: PageContext,
    interactions: Sequence[Mapping[str, Any]],
    approvals: Sequence[Mapping[str, Any]] = (),
) -> Element:
    """Return everything waiting on a person, across every run (FR-008)."""
    by_id = {str(approval.get("approval_id", "")): approval for approval in approvals}
    cards = [
        interaction_card(context, interaction, approval=by_id.get(_approval_id(interaction)))
        for interaction in interactions
    ]
    return element(
        "div",
        heading(1, context.text("interactions.heading")),
        *(cards or [element("p", context.text("interactions.empty"), class_="muted")]),
    )


def _approval_id(interaction: Mapping[str, Any]) -> str:
    """Return the approval an interaction refers to, if it refers to one."""
    return str(interaction.get("approval_id") or interaction.get("interaction_id") or "")


def interaction_card(
    context: PageContext,
    interaction: Mapping[str, Any],
    *,
    approval: Mapping[str, Any] | None = None,
) -> Element:
    """Return one waiting item, as an approval or as a question."""
    if str(interaction.get("kind", "")) == APPROVAL_KIND:
        return approval_card(context, interaction, approval=approval)
    return question_card(context, interaction)


def question_card(context: PageContext, interaction: Mapping[str, Any]) -> Element:
    """Return a question, with its structured options and a free-text answer.

    Both, not either. The options are what the agent believes the answers are
    and are usually right; the free-text field is what makes the case where it
    is wrong recoverable without abandoning the run.
    """
    interaction_id = str(interaction.get("interaction_id", ""))
    options = [str(option) for option in interaction.get("options") or ()]
    return card(
        heading(2, context.text("interactions.question")),
        element("p", str(interaction.get("text", ""))),
        element("p", str(interaction.get("reason", "")), class_="muted")
        if interaction.get("reason")
        else None,
        _closed_notice(context, interaction),
        action_control(
            context.viewer,
            Action.ANSWER_QUESTION,
            lambda: form(
                element(
                    "fieldset",
                    element("legend", context.text("interactions.answer_label")),
                    *[
                        element(
                            "div",
                            element(
                                "input",
                                id=f"{interaction_id}-{index}",
                                name="selected_option",
                                type="radio",
                                value=option,
                            ),
                            element("label", option, for_=f"{interaction_id}-{index}"),
                            class_="field field--inline",
                        )
                        for index, option in enumerate(options)
                    ],
                )
                if options
                else None,
                form_field(
                    identifier=f"{interaction_id}-text",
                    name="text",
                    label=context.text("interactions.answer_label"),
                    kind="textarea",
                    required=not options,
                ),
                element(
                    "button", context.text("interactions.answer"), type="submit", class_="primary"
                ),
                action=f"/interactions/{interaction_id}/answer",
                label=context.text("interactions.answer"),
            ),
        )
        if interaction.get("is_open", True)
        else None,
        data_interaction=interaction_id,
        data_kind="question",
    )


def approval_card(
    context: PageContext,
    interaction: Mapping[str, Any],
    *,
    approval: Mapping[str, Any] | None = None,
) -> Element:
    """Return a change awaiting approval, with everything a decision rests on (FR-009).

    Every one of the six sections is present whether or not there is data for
    it. A missing rollback plan is the single most important thing on this card
    and the easiest to render as nothing at all.
    """
    detail = approval or {}
    interaction_id = str(interaction.get("interaction_id", ""))
    raw_arguments = detail.get("arguments")
    arguments: Mapping[str, Any] = raw_arguments if isinstance(raw_arguments, Mapping) else {}

    return card(
        heading(2, context.text("interactions.approval")),
        element("p", str(interaction.get("text") or detail.get("summary", ""))),
        definitions(
            [
                (
                    context.text("interactions.target"),
                    value_or_dash(context, detail.get("action") or arguments.get("target")),
                ),
                (
                    context.text("interactions.current_state"),
                    value_or_dash(context, arguments.get("current_state")),
                ),
                (context.text("interactions.proposed"), _arguments_block(context, arguments)),
                (
                    context.text("interactions.blast_radius"),
                    _blast_radius(context, detail.get("blast_radius")),
                ),
                (context.text("interactions.rollback"), _rollback(context, detail)),
                (
                    context.text("interactions.evidence"),
                    _evidence(context, detail.get("evidence")),
                ),
            ]
        ),
        _closed_notice(context, interaction),
        _decision_controls(context, interaction_id) if interaction.get("is_open", True) else None,
        danger=str(detail.get("side_effect_level", "")).startswith("destructive"),
        data_interaction=interaction_id,
        data_kind="approval",
    )


def _decision_controls(context: PageContext, interaction_id: str) -> Element:
    """Return approve and reject, for a viewer who may decide."""
    return element(
        "div",
        action_control(
            context.viewer,
            Action.APPROVE_CHANGE,
            lambda: form(
                element(
                    "button", context.text("interactions.approve"), type="submit", class_="primary"
                ),
                action=f"/interactions/{interaction_id}/approve",
                label=context.text("interactions.approve"),
            ),
        ),
        action_control(
            context.viewer,
            Action.REJECT_CHANGE,
            lambda: form(
                form_field(
                    identifier=f"{interaction_id}-reason",
                    name="reason",
                    label=context.text("interactions.reject_reason"),
                    required=True,
                ),
                element(
                    "button", context.text("interactions.reject"), type="submit", class_="danger"
                ),
                action=f"/interactions/{interaction_id}/reject",
                label=context.text("interactions.reject"),
            ),
        ),
        class_="decisions",
    )


def _closed_notice(context: PageContext, interaction: Mapping[str, Any]) -> Element | None:
    """Return the notice that this was decided somewhere else (FR-010, SC-003).

    The console does not poll to find this out. A decision made in chat closes
    the interaction, the run's event stream carries that, and the open page
    replaces the card with this — which is what "without a manual refresh"
    means in a surface that streams.
    """
    if interaction.get("is_open", True):
        return None
    return element(
        "p",
        context.text("interactions.closed_elsewhere"),
        role="status",
        class_="notice",
        data_closed="true",
    )


def rollback_card(context: PageContext, approval: Mapping[str, Any], *, until: str = "") -> Element:
    """Return the rollback control for an executed remediation (FR-011)."""
    approval_id = str(approval.get("approval_id", ""))
    return card(
        heading(2, context.text("interactions.rollback")),
        _rollback(context, approval),
        element("p", context.text("interactions.rollback_window", until=until), class_="muted")
        if until
        else None,
        action_control(
            context.viewer,
            Action.ROLLBACK,
            lambda: form(
                element(
                    "button",
                    context.text("interactions.rollback_action"),
                    type="submit",
                    class_="danger",
                ),
                action=f"/approvals/{approval_id}/rollback",
                label=context.text("interactions.rollback_action"),
            ),
        ),
        data_approval=approval_id,
    )


def _arguments_block(context: PageContext, arguments: Mapping[str, Any]) -> Child:
    """Return the call as it would be made, field by field."""
    if not arguments:
        return context.text("common.none")
    return element(
        "ul",
        *[
            element("li", element("code", f"{name}"), ": ", str(value))
            for name, value in sorted(arguments.items())
        ],
    )


def _blast_radius(context: PageContext, radius: Any) -> Child:
    """Return what this change would reach, nearest first."""
    if not isinstance(radius, list) or not radius:
        return context.text("common.none")
    return element(
        "ul",
        *[
            element(
                "li",
                f"{_node_name(entry)} ({entry.get('depth', '?')} hop"
                f"{'' if entry.get('depth') == 1 else 's'})",
            )
            for entry in radius
            if isinstance(entry, Mapping)
        ],
    )


def _node_name(entry: Mapping[str, Any]) -> str:
    """Return a blast-radius entry's node name."""
    node = entry.get("node")
    if isinstance(node, Mapping):
        return str(node.get("name") or node.get("node_id", ""))
    return str(entry.get("node_id", ""))


def _rollback(context: PageContext, detail: Mapping[str, Any]) -> Child:
    """Return the stored rollback plan, or say plainly that there is none."""
    plan = detail.get("rollback_plan")
    if not isinstance(plan, Mapping):
        return element("strong", context.text("interactions.no_rollback"))
    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        return element("strong", context.text("interactions.no_rollback"))
    return element(
        "ol",
        *[
            element(
                "li",
                f"{step.get('description', '')} ",
                element("code", str(step.get("capability", ""))),
            )
            for step in steps
            if isinstance(step, Mapping)
        ],
    )


def _evidence(context: PageContext, evidence: Any) -> Child:
    """Return the observations behind the proposal (Article I)."""
    if not isinstance(evidence, list) or not evidence:
        return context.text("common.none")
    return element(
        "ul",
        *[
            element(
                "li", str(item.get("summary", item)) if isinstance(item, Mapping) else str(item)
            )
            for item in evidence
        ],
    )


__all__ = [
    "APPROVAL_KIND",
    "approval_card",
    "interaction_card",
    "interaction_queue_body",
    "question_card",
    "rollback_card",
]
