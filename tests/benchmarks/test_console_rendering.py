"""SC-001 and SC-008: what the console costs on a transcript and a tree that are big.

Both numbers are about incidents. A ten-thousand-event transcript is what a long
investigation actually produces, and a five-hundred-node organisation is what a
company that bought this product actually has — so a console that is comfortable
on a fixture and stalls on either is a console nobody uses during the hour it
was built for.

The property being measured is not "fast". It is **flat**: windowed rendering
means the cost of a transcript does not depend on the transcript's length, so
the scaling assertion is the one that would catch a regression. A renderer that
started touching every event again would still be fast enough at a hundred and
would fail here.
"""

from __future__ import annotations

import time

import pytest

from config.constants.surfaces import (
    CONSOLE_ORG_TREE_BENCHMARK_NODES,
    CONSOLE_ORG_TREE_BUDGET_MS,
    CONSOLE_TRANSCRIPT_BENCHMARK_EVENTS,
    CONSOLE_TRANSCRIPT_RENDER_BUDGET_MS,
    CONSOLE_TRANSCRIPT_SCALING_TOLERANCE,
)
from surfaces.console.pages.config import org_tree
from surfaces.console.pages.shell import PageContext
from surfaces.console.transcript import TranscriptEvent, render_transcript
from surfaces.console.virtualisation import window_at_end

pytestmark = [pytest.mark.benchmark]

#: How many times each measurement runs. Enough that one scheduling hiccup does
#: not decide the result, few enough that the suite stays fast.
REPEATS = 20


def _events(count: int) -> tuple[TranscriptEvent, ...]:
    """Return a transcript of ``count`` events, of the kinds a real run produces."""
    kinds = ("turn_completed", "capability_called", "evidence_observed", "guardrail_action")
    return tuple(
        TranscriptEvent(
            run_id="run-benchmark",
            kind=kinds[sequence % len(kinds)],
            sequence=sequence,
            occurred_at="2026-05-01T08:00:00+00:00",
            payload={
                "text": f"step {sequence}: the connection pool is at {sequence % 20} of 20",
                "capability": "datadog.search_logs",
                "arguments": {"query": f"service:checkout status:error page:{sequence}"},
                "result": {"count": sequence, "sample": ["a", "b", "c"]},
            },
        )
        for sequence in range(count)
    )


def _median_ms(measure: object, repeats: int = REPEATS) -> float:
    """Return the median wall time of ``repeats`` calls, in milliseconds."""
    assert callable(measure)
    timings: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        measure()
        timings.append((time.perf_counter() - started) * 1000.0)
    timings.sort()
    return timings[len(timings) // 2]


def test_a_ten_thousand_event_transcript_renders_within_the_budget() -> None:
    events = _events(CONSOLE_TRANSCRIPT_BENCHMARK_EVENTS)
    window = window_at_end(len(events))

    elapsed = _median_ms(lambda: render_transcript(events, window=window).render())

    assert elapsed < CONSOLE_TRANSCRIPT_RENDER_BUDGET_MS, (
        f"{CONSOLE_TRANSCRIPT_BENCHMARK_EVENTS} events took {elapsed:.1f}ms, over the "
        f"{CONSOLE_TRANSCRIPT_RENDER_BUDGET_MS}ms budget"
    )


def test_rendering_cost_does_not_grow_with_the_length_of_the_transcript() -> None:
    """The property virtualisation exists for, asserted rather than assumed."""
    small = _events(100)
    large = _events(CONSOLE_TRANSCRIPT_BENCHMARK_EVENTS)
    small_window = window_at_end(len(small))
    large_window = window_at_end(len(large))

    small_ms = _median_ms(lambda: render_transcript(small, window=small_window).render())
    large_ms = _median_ms(lambda: render_transcript(large, window=large_window).render())

    assert large_ms < max(small_ms, 0.5) * CONSOLE_TRANSCRIPT_SCALING_TOLERANCE, (
        f"100 events took {small_ms:.2f}ms and "
        f"{CONSOLE_TRANSCRIPT_BENCHMARK_EVENTS} took {large_ms:.2f}ms — the renderer is "
        f"touching events outside the window"
    )


def test_the_number_of_elements_rendered_is_the_window_not_the_transcript() -> None:
    """The structural half of SC-001, which no timing can be fooled about.

    A transcript shorter than the window renders whole — that is correct, and it
    is why the comparison is between two transcripts that are both longer than
    it. Above the window size, the rendered count stops moving.
    """
    large = render_transcript(
        _events(CONSOLE_TRANSCRIPT_BENCHMARK_EVENTS),
        window=window_at_end(CONSOLE_TRANSCRIPT_BENCHMARK_EVENTS),
    )
    medium = render_transcript(_events(1_000), window=window_at_end(1_000))
    short = render_transcript(_events(20), window=window_at_end(20))

    assert large.attribute("data-rendered") == medium.attribute("data-rendered")
    assert large.attribute("data-total") == str(CONSOLE_TRANSCRIPT_BENCHMARK_EVENTS)
    assert len(large.find("li")) < 200
    assert short.attribute("data-rendered") == "20"


def test_a_five_hundred_node_org_tree_is_built_within_the_interaction_budget() -> None:
    nodes = _org_nodes(CONSOLE_ORG_TREE_BENCHMARK_NODES)
    context = PageContext()

    elapsed = _median_ms(lambda: org_tree(context, nodes, selected="team-250").render())

    assert elapsed < CONSOLE_ORG_TREE_BUDGET_MS, (
        f"{CONSOLE_ORG_TREE_BENCHMARK_NODES} nodes took {elapsed:.1f}ms, over the "
        f"{CONSOLE_ORG_TREE_BUDGET_MS}ms budget"
    )


def test_every_node_of_a_five_hundred_node_tree_is_actually_present() -> None:
    """A tree that is fast because it dropped half the organisation is not fast."""
    nodes = _org_nodes(CONSOLE_ORG_TREE_BENCHMARK_NODES)

    rendered = org_tree(PageContext(), nodes)

    assert rendered.attribute("data-nodes") == str(CONSOLE_ORG_TREE_BENCHMARK_NODES)
    assert len(rendered.find("a")) == CONSOLE_ORG_TREE_BENCHMARK_NODES


def _org_nodes(count: int) -> tuple[dict[str, object], ...]:
    """Return a three-level organisation of ``count`` nodes: root, divisions, teams.

    Shaped rather than flat, because a flat list would let a quadratic tree
    builder look linear — the cost of the naive implementation is in scanning
    for each node's children at every level.
    """
    nodes: list[dict[str, object]] = [
        {"node_id": "acme", "kind": "organisation", "name": "Acme", "parent_id": None}
    ]
    divisions = max(1, int(count**0.5))
    for index in range(1, count):
        if index <= divisions:
            nodes.append(
                {
                    "node_id": f"div-{index}",
                    "kind": "division",
                    "name": f"Division {index}",
                    "parent_id": "acme",
                }
            )
        else:
            nodes.append(
                {
                    "node_id": f"team-{index}",
                    "kind": "team",
                    "name": f"Team {index}",
                    "parent_id": f"div-{(index % divisions) + 1}",
                }
            )
    return tuple(nodes)
