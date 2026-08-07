"""The run list, and the one detail component that serves live and replay alike.

``run_detail_body`` takes the events and a flag saying whether the run is still
going. Nothing else differs between watching and reviewing, which is the point:
a replayed investigation is rendered by the same code that rendered it live, so
it cannot look different — and the trace stays trustworthy as a review artefact
precisely because there is no second rendering that could disagree with it.

The attention state on the list is the column an on-call engineer scans first. A
run that is waiting on a person is not failing and is not progressing, and the
list is the only place that distinction is visible before opening something.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from surfaces.console.html import Child, Element, element, fragment
from surfaces.console.pages.shell import (
    PageContext,
    badge,
    card,
    definitions,
    form,
    form_field,
    heading,
    table,
    value_or_dash,
)
from surfaces.console.permissions import Action, action_control
from surfaces.console.transcript import TranscriptEvent, render_transcript
from surfaces.console.virtualisation import Window

#: The statuses a filter offers. Read from the runs the API returned rather than
#: hard-coded would be tempting and wrong: a status nobody has produced yet is
#: still one somebody wants to filter for.
STATUS_OPTIONS = ("running", "waiting", "completed", "failed", "cancelled")

TRIGGER_OPTIONS = ("interactive", "webhook", "schedule", "chat")


def _attention(context: PageContext, run: Mapping[str, Any]) -> Child:
    """Return whether this run is waiting on a person, in words."""
    waiting = bool(run.get("awaiting_interaction") or run.get("status") == "waiting")
    return badge(
        context.text("runs.attention_yes" if waiting else "runs.attention_no"),
        kind="attention" if waiting else "",
    )


def filters(context: PageContext, *, selected: Mapping[str, str] | None = None) -> Element:
    """Return the run filters (FR-001)."""
    chosen = dict(selected or {})
    return card(
        element(
            "form",
            element(
                "fieldset",
                element("legend", context.text("runs.filter.legend")),
                _select(
                    context,
                    identifier="status",
                    label=context.text("runs.filter.status"),
                    options=STATUS_OPTIONS,
                    value=chosen.get("status", ""),
                ),
                _select(
                    context,
                    identifier="trigger",
                    label=context.text("runs.filter.trigger"),
                    options=TRIGGER_OPTIONS,
                    value=chosen.get("trigger", ""),
                ),
                form_field(
                    identifier="team",
                    label=context.text("runs.filter.team"),
                    value=chosen.get("team", ""),
                ),
                form_field(
                    identifier="since",
                    label=context.text("runs.filter.since"),
                    kind="date",
                    value=chosen.get("since", ""),
                ),
                element(
                    "div",
                    element(
                        "input",
                        id="attention",
                        name="attention",
                        type="checkbox",
                        checked=bool(chosen.get("attention")),
                    ),
                    element("label", context.text("runs.filter.attention"), for_="attention"),
                    class_="field field--inline",
                ),
            ),
            element("button", context.text("runs.filter.apply"), type="submit"),
            action="/runs",
            method="get",
            aria_label=context.text("runs.filter.legend"),
        )
    )


def _select(
    context: PageContext, *, identifier: str, label: str, options: Sequence[str], value: str
) -> Element:
    """Return a labelled select with an "any" option first."""
    return element(
        "div",
        element("label", label, for_=identifier),
        element(
            "select",
            element("option", context.text("common.none"), value=""),
            *[
                element("option", option, value=option, selected=option == value)
                for option in options
            ],
            id=identifier,
            name=identifier,
        ),
        class_="field",
    )


def schedules_panel(context: PageContext, schedules: Sequence[Mapping[str, Any]]) -> Element:
    """Return the recurring investigations, and the control to add one.

    On the runs area rather than in configuration: a schedule is an
    investigation that has not happened yet, and the person who wants one is
    already looking at the ones that have.
    """
    return element(
        "section",
        heading(2, context.text("runs.schedules")),
        table(
            caption=context.text("runs.schedules"),
            columns=[
                context.text("runs.objective_label"),
                context.text("runs.schedule_cron"),
                context.text("runs.schedule_next"),
            ],
            rows=[
                [
                    value_or_dash(context, schedule.get("objective")),
                    value_or_dash(context, schedule.get("cron")),
                    value_or_dash(context, schedule.get("next_run_at")),
                ]
                for schedule in schedules
            ],
            empty=context.text("runs.schedule_empty"),
        ),
        action_control(
            context.viewer,
            Action.MANAGE_SCHEDULE,
            lambda: card(
                form(
                    form_field(
                        identifier="schedule_objective",
                        name="objective",
                        label=context.text("runs.schedule_objective"),
                        required=True,
                    ),
                    form_field(
                        identifier="schedule_cron",
                        name="cron",
                        label=context.text("runs.schedule_cron"),
                        required=True,
                    ),
                    element("button", context.text("runs.schedule_add"), type="submit"),
                    action="/runs/schedules",
                    label=context.text("runs.schedule_add"),
                )
            ),
        ),
        aria_label=context.text("runs.schedules"),
    )


def run_list_body(
    context: PageContext,
    runs: Sequence[Mapping[str, Any]],
    *,
    selected: Mapping[str, str] | None = None,
    schedules: Sequence[Mapping[str, Any]] = (),
) -> Element:
    """Return the run list with its filters and the start control (FR-001, FR-006)."""
    columns = [
        context.text("runs.column.run"),
        context.text("runs.column.status"),
        context.text("runs.column.trigger"),
        context.text("runs.column.started"),
        context.text("runs.column.cost"),
        context.text("runs.column.outcome"),
        context.text("runs.column.attention"),
    ]
    rows: list[Sequence[Child]] = [
        [
            element("a", str(run.get("run_id", "")), href=f"/runs/{run.get('run_id', '')}"),
            value_or_dash(context, run.get("status")),
            value_or_dash(context, run.get("trigger")),
            value_or_dash(context, run.get("started_at")),
            value_or_dash(context, run.get("cost")),
            value_or_dash(context, run.get("summary")),
            _attention(context, run),
        ]
        for run in runs
    ]

    return element(
        "div",
        heading(1, context.text("runs.heading")),
        filters(context, selected=selected),
        _start_form(context),
        table(
            caption=context.text("runs.heading"),
            columns=columns,
            rows=rows,
            empty=context.text("runs.empty"),
        ),
        schedules_panel(context, schedules),
    )


def _start_form(context: PageContext) -> Element | None:
    """Return the start-an-investigation form, for those who may start one."""
    return action_control(
        context.viewer,
        Action.START_INVESTIGATION,
        lambda: card(
            form(
                form_field(
                    identifier="objective",
                    label=context.text("runs.objective_label"),
                    kind="textarea",
                    required=True,
                ),
                element("button", context.text("runs.start"), type="submit", class_="primary"),
                action="/runs",
                label=context.text("runs.start"),
            )
        ),
    )


def cost_panel(context: PageContext, cost: Mapping[str, Any]) -> Element:
    """Return what one run consumed (Article II made visible rather than implied)."""
    return card(
        heading(2, context.text("runs.cost")),
        definitions(
            [
                (
                    context.text("runs.cost.tokens"),
                    value_or_dash(context, cost.get("total_tokens")),
                ),
                (context.text("runs.cost.total"), value_or_dash(context, cost.get("total_cost"))),
                (context.text("runs.cost.turns"), value_or_dash(context, cost.get("turns"))),
            ]
        ),
    )


def run_detail_body(
    context: PageContext,
    run: Mapping[str, Any],
    events: Sequence[TranscriptEvent],
    *,
    is_live: bool,
    window: Window | None = None,
    expanded: Sequence[int] = (),
    interactions: Sequence[Mapping[str, Any]] = (),
    reconnected: bool = False,
) -> Element:
    """Return one run, live or replayed, through the same component (FR-002).

    ``is_live`` changes two things and nothing else: the sentence at the top,
    and whether the transcript region is a polite live region. The events, the
    trace, the sub-agent expansion, the evidence, and the cost are rendered
    identically either way.
    """
    from surfaces.console.pages.interactions import interaction_card

    run_id = str(run.get("run_id", ""))
    return element(
        "div",
        heading(1, run_id),
        definitions(
            [
                (context.text("runs.column.status"), value_or_dash(context, run.get("status"))),
                (context.text("runs.column.trigger"), value_or_dash(context, run.get("trigger"))),
                (
                    context.text("runs.column.started"),
                    value_or_dash(context, run.get("started_at")),
                ),
                (
                    context.text("runs.column.outcome"),
                    value_or_dash(context, run.get("summary")),
                ),
            ]
        ),
        element("p", context.text("runs.live" if is_live else "runs.replay"), class_="muted"),
        element("p", context.text("runs.reconnected"), role="status") if reconnected else None,
        _run_controls(context, run_id, is_live=is_live),
        # Pending interactions appear here as well as in the queue (FR-008,
        # T029): somebody watching a run should not have to go and find the
        # question the run is blocked on.
        element(
            "section",
            heading(2, context.text("interactions.on_run")),
            *[interaction_card(context, interaction) for interaction in interactions],
            aria_label=context.text("interactions.on_run"),
        )
        if interactions
        else None,
        element(
            "section",
            heading(2, context.text("runs.title")),
            render_transcript(events, window=window, expanded=expanded),
            aria_label=context.text("runs.title"),
            aria_live="polite" if is_live else None,
            data_live="true" if is_live else "false",
        ),
        cost_panel(context, run.get("cost") or {}),
    )


def _run_controls(context: PageContext, run_id: str, *, is_live: bool) -> Element:
    """Return the mid-run controls this viewer may use (FR-006)."""
    return fragment(
        action_control(
            context.viewer,
            Action.ADD_CONTEXT,
            lambda: card(
                form(
                    form_field(
                        identifier="context",
                        label=context.text("runs.context_label"),
                        kind="textarea",
                        required=True,
                    ),
                    element("button", context.text("runs.add_context"), type="submit"),
                    action=f"/runs/{run_id}/context",
                    label=context.text("runs.add_context"),
                )
            ),
        )
        if is_live
        else None,
        action_control(
            context.viewer,
            Action.CANCEL_INVESTIGATION,
            lambda: form(
                element("button", context.text("runs.cancel"), type="submit", class_="danger"),
                action=f"/runs/{run_id}/cancel",
                label=context.text("runs.cancel"),
            ),
        )
        if is_live
        else None,
        action_control(
            context.viewer,
            Action.TAKE_OVER,
            lambda: form(
                element("button", context.text("runs.take_over"), type="submit"),
                action=f"/runs/{run_id}/take-over",
                label=context.text("runs.take_over"),
            ),
        )
        if is_live
        else None,
    )


__all__ = [
    "STATUS_OPTIONS",
    "TRIGGER_OPTIONS",
    "cost_panel",
    "filters",
    "run_detail_body",
    "run_list_body",
]
