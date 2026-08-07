"""What an investigation looks like while it runs, and how it asks for something.

Rendering is the first half: thoughts, capability calls, sub-agent activity, and
results are rendered as they occur, from the pipeline's own events rather than
from a second narration. Interaction is the second: a question or an approval is
presented inline and answered in place, through the registry that owns
first-writer-wins.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta

import pytest

from config.constants.surfaces import SURFACE_REPL
from core.agent.interaction.models import (
    Answer,
    ApprovalInteraction,
    InteractionKind,
    InteractionState,
    question,
)
from core.agent.interaction.registry import InteractionRegistry
from core.pipeline.streaming import PipelineEvent, PipelineEventKind
from surfaces.cli.errors import NotFoundError
from surfaces.cli.output.degradation import Terminal
from surfaces.repl.interaction import InlineInteractions, only_one, render
from surfaces.repl.session import ReplSession
from surfaces.repl.streaming import StreamRenderer, describe, label_of, render_events

pytestmark = pytest.mark.unit

NOW = datetime(2026, 3, 14, 9, 0, tzinfo=UTC)


def _stream() -> list[PipelineEvent]:
    """Return one investigation's worth of events, one of each kind that matters."""
    return [
        PipelineEvent(kind=PipelineEventKind.THOUGHT, sequence=1, text="the timing fits a deploy"),
        PipelineEvent(
            kind=PipelineEventKind.TOOL_START, sequence=2, capability="datadog_query", call_id="c1"
        ),
        PipelineEvent(
            kind=PipelineEventKind.TOOL_END,
            sequence=3,
            capability="datadog_query",
            call_id="c1",
            text="p99 doubled at 14:02",
        ),
        PipelineEvent(kind=PipelineEventKind.SUBAGENT_START, sequence=4, subagent="log-reader"),
        PipelineEvent(
            kind=PipelineEventKind.SUBAGENT_END, sequence=5, subagent="log-reader", text="done"
        ),
        PipelineEvent(kind=PipelineEventKind.EVIDENCE, sequence=6, evidence_id="ev-1"),
        PipelineEvent(kind=PipelineEventKind.RESULT, sequence=7, text="the pool was halved"),
    ]


def test_every_event_kind_has_a_label() -> None:
    # A closed enum with a closed mapping. A fourteenth kind that rendered as
    # nothing would be an event nobody sees.
    for kind in PipelineEventKind:
        assert label_of(kind)


def test_a_piped_stream_gets_one_line_per_event() -> None:
    out = io.StringIO()

    render_events(_stream(), out, terminal=Terminal(piped=True))

    lines = [line for line in out.getvalue().splitlines() if line.strip()]
    # Seven events, and the result takes a second line for its body.
    assert len(lines) == 8
    assert "\r" not in out.getvalue(), "a pipe must not receive cursor movement"


def test_a_piped_stream_carries_no_escape_sequences() -> None:
    out = io.StringIO()

    render_events(_stream(), out, terminal=Terminal(piped=True))

    assert "\x1b" not in out.getvalue()


def test_an_interactive_terminal_overwrites_its_status_line() -> None:
    out = io.StringIO()

    render_events(_stream(), out, terminal=Terminal(interactive=True, piped=False, width=80))

    assert "\r" in out.getvalue()


def test_a_result_is_shown_in_full_even_on_an_interactive_terminal() -> None:
    # A result the operator has to scroll back for is a result they will not
    # read, so it is never a transient line.
    out = io.StringIO()
    long_result = "the connection pool was halved by the 14:02 deploy. " * 6

    render_events(
        [PipelineEvent(kind=PipelineEventKind.RESULT, text=long_result)],
        out,
        terminal=Terminal(interactive=True, piped=False, width=80),
    )

    assert long_result in out.getvalue()


def test_the_renderer_tallies_what_a_status_line_needs() -> None:
    out = io.StringIO()

    renderer = render_events(_stream(), out, terminal=Terminal(piped=True))

    assert renderer.tool_calls == 1
    assert renderer.evidence_seen == ["ev-1"]
    assert renderer.result == "the pool was halved"
    assert renderer.errors == []
    assert renderer.status() == {
        "tool_calls": 1,
        "evidence": 1,
        "errors": 0,
        "has_result": True,
    }


def test_a_failed_tool_call_is_described_as_failed() -> None:
    event = PipelineEvent(
        kind=PipelineEventKind.TOOL_END, capability="datadog_query", failed=True, text="401"
    )

    assert "failed" in describe(event)


def test_an_error_is_tallied_and_shown() -> None:
    out = io.StringIO()

    renderer = render_events(
        [PipelineEvent(kind=PipelineEventKind.ERROR, text="the provider timed out")],
        out,
        terminal=Terminal(piped=True),
    )

    assert renderer.errors == ["the provider timed out"]
    assert "the provider timed out" in out.getvalue()


def test_no_rendered_line_exceeds_the_terminal_width() -> None:
    out = io.StringIO()
    wordy = PipelineEvent(kind=PipelineEventKind.THOUGHT, text="x" * 400)

    render_events([wordy], out, terminal=Terminal(width=80, piped=True))

    for line in out.getvalue().splitlines():
        assert len(line) <= 80, line


def test_finishing_closes_an_open_transient_line() -> None:
    out = io.StringIO()
    renderer = StreamRenderer(out=out, terminal=Terminal(interactive=True, piped=False))
    renderer.handle(PipelineEvent(kind=PipelineEventKind.THOUGHT, text="thinking"))

    renderer.finish()

    assert out.getvalue().endswith("\n")


# -- interaction --------------------------------------------------------------


def _inline() -> tuple[InlineInteractions, InteractionRegistry, io.StringIO]:
    """Return an inline presenter over an empty registry."""
    out = io.StringIO()
    registry = InteractionRegistry(run_id="run-0001", clock=lambda: NOW)
    inline = InlineInteractions(
        registry=registry,
        out=out,
        session=ReplSession(session_id="sess-1"),
        principal_id="alex",
        terminal=Terminal(),
    )
    return inline, registry, out


def _approval() -> ApprovalInteraction:
    """Return one approval waiting on somebody."""
    return ApprovalInteraction(
        interaction_id="int-approve",
        run_id="run-0001",
        raised_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
        action="scale checkout to 12 replicas",
        diff="replicas: 8 -> 12",
        blast_radius="the checkout deployment in eu-west-1",
        rollback_plan="scale back to 8",
        summary="scale checkout",
    )


def test_a_question_is_presented_with_its_reason_and_options() -> None:
    inline, registry, out = _inline()
    asked = question(
        interaction_id="int-q",
        run_id="run-0001",
        text="which region is affected?",
        reason="it decides which cluster I look at next",
        options=("eu-west-1", "us-east-1"),
        at=NOW,
    )
    registry.raise_interaction(asked)

    inline.show(asked)

    written = out.getvalue()
    assert "which region is affected?" in written
    assert "it decides which cluster I look at next" in written
    assert "eu-west-1" in written
    assert "/answer int-q" in written


def test_an_approval_shows_the_diff_the_blast_radius_and_the_rollback_plan() -> None:
    # All three, every time. Abbreviating one would be making the judgement the
    # reviewer is there to make.
    rendered = render(_approval(), Terminal())

    assert "replicas: 8 -> 12" in rendered
    assert "the checkout deployment in eu-west-1" in rendered
    assert "scale back to 8" in rendered


def test_an_approval_with_no_rollback_plan_says_it_is_not_reversible() -> None:
    from dataclasses import replace

    rendered = render(replace(_approval(), rollback_plan=""), Terminal())

    assert "not reversible" in rendered


def test_answering_closes_the_question_and_attributes_it() -> None:
    inline, registry, _ = _inline()
    registry.raise_interaction(
        question(interaction_id="int-q", run_id="run-0001", text="which region?", at=NOW)
    )

    resolution = inline.answer("int-q", "eu-west-1")

    assert resolution.won
    closed = registry.get("int-q")
    assert closed.state is InteractionState.ANSWERED
    assert closed.answer is not None
    assert closed.answer.principal == "alex"
    assert closed.answer.surface == SURFACE_REPL


def test_answering_clears_what_the_session_was_waiting_on() -> None:
    inline, registry, _ = _inline()
    asked = question(interaction_id="int-q", run_id="run-0001", text="which region?", at=NOW)
    registry.raise_interaction(asked)
    inline.show(asked)
    assert inline.session.awaiting == ("int-q",)

    inline.answer("int-q", "eu-west-1")

    assert inline.session.awaiting == ()


def test_answering_something_that_was_never_asked_names_it() -> None:
    inline, _, _ = _inline()

    with pytest.raises(NotFoundError, match="int-nope"):
        inline.answer("int-nope", "anything")


def test_losing_the_race_is_reported_with_who_won() -> None:
    # Two surfaces, one question. The loser is told who answered, not only that
    # they were late.
    inline, registry, out = _inline()
    registry.raise_interaction(
        question(interaction_id="int-q", run_id="run-0001", text="which region?", at=NOW)
    )
    registry.resolve("int-q", Answer(text="us-east-1", principal="sam", surface="chat"))

    resolution = inline.answer("int-q", "eu-west-1")

    assert resolution.lost
    assert resolution.answered_by == "sam"
    assert "too late" in out.getvalue()
    assert "sam" in out.getvalue()


@pytest.mark.parametrize("decision", ["approve", "decline", "APPROVE", " Decline "])
def test_an_approval_accepts_only_the_two_words(decision: str) -> None:
    inline, registry, _ = _inline()
    registry.raise_interaction(_approval())

    resolution = inline.approve("int-approve", decision)

    assert resolution.won
    assert resolution.interaction.answer is not None
    assert resolution.interaction.answer.selected_option == decision.strip().lower()


@pytest.mark.parametrize("decision", ["yes", "yeah probably", "y", "ok", "sure", "1"])
def test_anything_else_is_refused_rather_than_read_generously(decision: str) -> None:
    # The one place a generous reading applies a production change nobody
    # agreed to.
    inline, registry, _ = _inline()
    registry.raise_interaction(_approval())

    with pytest.raises(ValueError, match="not a decision"):
        inline.approve("int-approve", decision)

    assert registry.get("int-approve").state is InteractionState.PENDING


def test_a_takeover_closes_everything_open() -> None:
    # A live question on a run somebody has taken over is a button that would
    # answer a run that has stopped listening.
    inline, registry, _ = _inline()
    registry.raise_interaction(
        question(interaction_id="int-q", run_id="run-0001", text="which region?", at=NOW)
    )
    registry.raise_interaction(_approval())

    closed = inline.takeover("I am driving")

    assert len(closed) == 2
    assert all(found.state is InteractionState.SUPERSEDED for found in registry.all_interactions)
    assert inline.session.awaiting == ()


def test_pending_can_be_filtered_by_kind() -> None:
    inline, registry, _ = _inline()
    registry.raise_interaction(
        question(interaction_id="int-q", run_id="run-0001", text="which region?", at=NOW)
    )
    registry.raise_interaction(_approval())

    assert len(inline.pending(InteractionKind.QUESTION)) == 1
    assert len(inline.pending(InteractionKind.APPROVAL)) == 1
    assert len(inline.pending()) == 2


def test_showing_nothing_pending_says_so() -> None:
    inline, _, out = _inline()

    assert inline.show_pending() == 0
    assert "nothing is waiting on you" in out.getvalue()


def test_one_pending_is_unambiguous_and_two_are_not() -> None:
    # What lets ``/approve approve`` work with one waiting and refuse with two.
    approval = _approval()

    assert only_one([approval]) is approval
    assert only_one([approval, approval]) is None
    assert only_one([]) is None
