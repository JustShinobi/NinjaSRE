"""The unified live-and-replay transcript, and the windowing it depends on."""

from __future__ import annotations

import pytest

from config.constants.security import MASK_TOKEN_PREFIX, MASK_TOKEN_SEPARATOR
from platform.runs.events import TraceEventKind
from surfaces.console.accessibility import audit_fragment
from surfaces.console.html import text_of
from surfaces.console.transcript import (
    MAX_INLINE_RESULT_CHARS,
    TranscriptEvent,
    masked_text,
    render_event,
    render_transcript,
)
from surfaces.console.virtualisation import (
    Window,
    slice_of,
    window_at_end,
    window_of,
)


def _event(sequence: int, kind: str = "turn_completed", **payload: object) -> TranscriptEvent:
    return TranscriptEvent(
        run_id="run-1",
        kind=kind,
        sequence=sequence,
        occurred_at="2026-05-01T08:00:00+00:00",
        payload=payload,
    )


# --- Windowing ----------------------------------------------------------------


def test_an_empty_list_produces_an_empty_window_rather_than_an_error() -> None:
    window = window_of(0)

    assert (window.start, window.count, window.before, window.after) == (0, 0, 0, 0)


def test_a_list_shorter_than_the_window_is_rendered_whole() -> None:
    window = window_of(5, size=100)

    assert window.is_whole
    assert (window.before, window.after) == (0, 0)


def test_a_window_never_runs_past_the_start_of_the_list() -> None:
    window = window_of(1_000, anchor=0, size=10, overscan=5)

    assert window.start == 0
    assert window.count == 20


def test_a_window_never_runs_past_the_end_of_the_list() -> None:
    window = window_of(1_000, anchor=999, size=10, overscan=5)

    assert window.stop == 1_000
    assert window.count == 20


def test_a_window_contains_the_anchor_with_a_margin_on_both_sides() -> None:
    window = window_of(1_000, anchor=500, size=10, overscan=5)

    assert window.contains(500)
    assert window.before > 0 and window.after > 0


def test_the_end_window_is_where_a_live_run_is_watched_from() -> None:
    window = window_at_end(1_000, size=10, overscan=5)

    assert window.stop == 1_000
    assert window.after == 0


def test_a_window_that_ran_past_its_list_cannot_be_constructed() -> None:
    with pytest.raises(ValueError, match="runs past"):
        Window(start=90, count=20, total=100)


def test_slicing_returns_exactly_what_the_window_selected() -> None:
    items = list(range(100))
    window = window_of(100, anchor=50, size=6, overscan=2)

    assert list(slice_of(items, window)) == items[window.start : window.stop]


# --- Rendering ----------------------------------------------------------------


def test_a_thought_is_rendered_with_its_text() -> None:
    rendered = render_event(_event(1, text="the pool halved at 14:02"))

    assert "the pool halved at 14:02" in text_of(rendered)


def test_a_capability_call_carries_its_arguments_and_its_result() -> None:
    rendered = render_event(
        _event(
            2,
            kind="capability_called",
            capability="datadog.search_logs",
            arguments={"query": "service:checkout"},
            result={"count": 42},
        )
    )

    shown = text_of(rendered)
    assert "datadog.search_logs" in shown
    assert "service:checkout" in shown
    assert "42" in shown


def test_a_large_result_is_truncated_rather_than_pasted_into_the_page() -> None:
    rendered = render_event(
        _event(3, kind="capability_called", capability="k8s.logs", result="x" * 50_000)
    )

    shown = text_of(rendered)
    assert len(shown) < 50_000
    assert "Truncated" in shown


@pytest.mark.parametrize("kind", [kind.value for kind in TraceEventKind])
def test_every_event_kind_the_platform_records_has_a_rendering(kind: str) -> None:
    rendered = render_event(_event(1, kind=kind, text="something happened"))

    assert text_of(rendered).strip()
    assert rendered.attribute("data-kind") == kind


def test_an_event_kind_from_a_newer_deployment_is_shown_rather_than_dropped() -> None:
    rendered = render_event(_event(1, kind="something_new", text="a thing"))

    assert "Something new" in text_of(rendered)


def test_a_subagent_dispatch_can_be_expanded_to_its_own_turns_and_calls() -> None:
    rendered = render_event(
        _event(
            4,
            kind="subagent_dispatched",
            turns=[
                {"run_id": "run-1", "kind": "turn_completed", "sequence": 41, "payload": {}},
                {
                    "run_id": "run-1",
                    "kind": "capability_called",
                    "sequence": 42,
                    "payload": {"capability": "k8s.describe_pod"},
                },
            ],
        ),
        expanded=True,
    )

    assert "2 nested turns" in text_of(rendered)
    assert "k8s.describe_pod" in text_of(rendered)
    assert rendered.find("details")[0].has("open")


def test_a_subagent_dispatch_is_closed_unless_the_reader_opened_it() -> None:
    rendered = render_event(_event(4, kind="subagent_dispatched", turns=[]))

    assert not rendered.find("details")[0].has("open")


# --- Masked identifiers (FR-027) ----------------------------------------------


def test_a_masking_token_is_marked_up_so_it_does_not_read_as_a_hostname() -> None:
    token = f"{MASK_TOKEN_PREFIX}POD{MASK_TOKEN_SEPARATOR}1"

    rendered = masked_text(f"the pod {token} restarted")

    marked = rendered.find("span")
    assert len(marked) == 1
    assert text_of(marked[0]) == token
    assert "authorisation" in str(marked[0].attribute("title"))


def test_text_with_no_token_is_left_exactly_as_it_was() -> None:
    assert text_of(masked_text("checkout-7d9f restarted")) == "checkout-7d9f restarted"


def test_the_console_never_replaces_a_token_with_a_real_identifier() -> None:
    token = f"{MASK_TOKEN_PREFIX}HOST{MASK_TOKEN_SEPARATOR}3"

    assert token in text_of(masked_text(token))


# --- The transcript as a whole -------------------------------------------------


def test_a_transcript_renders_only_the_window_and_says_what_is_outside_it() -> None:
    events = [_event(sequence, text=f"step {sequence}") for sequence in range(1_000)]

    rendered = render_transcript(events, window=window_of(1_000, anchor=500, size=10, overscan=5))

    assert rendered.attribute("data-total") == "1000"
    assert rendered.attribute("data-rendered") == "20"
    assert len(rendered.find("li")) == 20 + 2  # the window, plus a spacer each side


def test_a_short_transcript_has_no_spacers_at_all() -> None:
    rendered = render_transcript([_event(0), _event(1)])

    assert not [node for node in rendered.walk() if node.has("data-spacer")]


def test_a_spacer_says_how_many_events_it_stands_for() -> None:
    events = [_event(sequence) for sequence in range(500)]

    rendered = render_transcript(events, window=window_of(500, anchor=250, size=10, overscan=0))
    spacers = [node for node in rendered.walk() if node.has("data-spacer")]

    assert sum(int(str(node.attribute("data-count"))) for node in spacers) == 490


def test_a_transcript_is_a_list_a_screen_reader_can_navigate() -> None:
    rendered = render_transcript([_event(0, text="one")])

    assert rendered.tag == "ol"
    assert rendered.attribute("aria-label") == "Investigation transcript"
    assert audit_fragment(rendered).passed, audit_fragment(rendered).describe()


def test_a_transcript_of_a_run_with_calls_and_subagents_is_accessible() -> None:
    events = [
        _event(0, kind="run_started", text="started"),
        _event(1, kind="capability_called", capability="k8s.logs", arguments={"pod": "a"}),
        _event(2, kind="subagent_dispatched", turns=[]),
        _event(3, kind="run_finished", summary="done"),
    ]

    report = audit_fragment(render_transcript(events))

    assert report.passed, report.describe()


def test_the_bound_on_an_inline_result_is_a_named_constant_not_a_literal() -> None:
    assert MAX_INLINE_RESULT_CHARS > 0
