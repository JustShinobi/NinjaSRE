"""The golden cases that pin which rule a merged span is attributed to.

Overlapping matches have to collapse, because redacting the same characters
twice produces ``[REDACTED][REDACTED]`` and redacting them in the wrong order
produces a placeholder with half a secret still in it. Collapsing is easy. The
part that has to be *pinned* is which rule the collapsed span is reported
under, because that name is what an operator tunes against — a rule they cannot
see firing is a rule they cannot turn off.

The rule is: the representative is the **widest individual contributing match**,
ties broken by the earliest start and then by rule name. Widest rather than
first, because the widest match is the one whose author understood the shape
best; deterministic ties, because a merge that reported a different name on a
different dict ordering would make the audit trail unreproducible.

The action is resolved separately and does not follow the representative. A
``block`` that overlaps an ``audit`` is still a block: severity wins, or a
narrow blocking rule could be neutralised by writing a wider auditing one.
"""

from __future__ import annotations

import pytest

from platform.guardrails.engine import ScanMatch, merge_spans
from platform.guardrails.rules import GuardrailAction

pytestmark = [pytest.mark.unit]


def match(rule: str, start: int, end: int, action: str = "redact") -> ScanMatch:
    """Return one match, spelled short because these tests are mostly data."""
    return ScanMatch(
        rule=rule,
        action=GuardrailAction(action),
        start=start,
        end=end,
        replacement="[REDACTED]",
    )


def test_disjoint_matches_do_not_merge() -> None:
    """The control: nothing overlaps, so nothing collapses."""
    spans = merge_spans((match("a", 0, 5), match("b", 10, 15)))

    assert [(span.start, span.end, span.rule) for span in spans] == [
        (0, 5, "a"),
        (10, 15, "b"),
    ]


def test_same_start_overlap_is_attributed_to_the_wider_match() -> None:
    """Two rules fire at the same offset; the one that saw more is the name."""
    spans = merge_spans((match("narrow", 4, 9), match("wide", 4, 20)))

    assert len(spans) == 1
    assert (spans[0].start, spans[0].end) == (4, 20)
    assert spans[0].rule == "wide"


def test_a_contained_span_is_attributed_to_its_container() -> None:
    """A rule matching inside an already-matched span does not rename it."""
    spans = merge_spans((match("outer", 0, 30), match("inner", 12, 18)))

    assert len(spans) == 1
    assert (spans[0].start, spans[0].end) == (0, 30)
    assert spans[0].rule == "outer"


def test_a_chained_overlap_collapses_to_one_span() -> None:
    """A, B, and C overlap pairwise but not all three; the union is one span.

    The representative is the widest *individual* match, which is deliberately
    not the same as the widest merged span — no rule matched all twenty
    characters, and attributing them to one that did not would be a lie in the
    audit trail.
    """
    spans = merge_spans(
        (
            match("alpha", 0, 10),
            match("bravo", 6, 16),
            match("charlie", 14, 20),
        )
    )

    assert len(spans) == 1
    assert (spans[0].start, spans[0].end) == (0, 20)
    assert spans[0].rule == "alpha"


def test_equal_width_ties_break_on_the_earlier_start() -> None:
    """Two equally wide contributors: the earlier one names the span."""
    spans = merge_spans((match("later", 5, 15), match("earlier", 0, 10)))

    assert spans[0].rule == "earlier"


def test_equal_width_and_start_ties_break_on_the_rule_name() -> None:
    """The last tie-break, so the answer never depends on iteration order."""
    forwards = merge_spans((match("aaa", 0, 10), match("bbb", 0, 10)))
    backwards = merge_spans((match("bbb", 0, 10), match("aaa", 0, 10)))

    assert forwards[0].rule == backwards[0].rule == "aaa"


def test_input_order_does_not_change_the_result() -> None:
    """The merge is a function of the set, not of the sequence."""
    matches = (
        match("alpha", 0, 10),
        match("bravo", 6, 16),
        match("charlie", 14, 20),
        match("delta", 40, 44),
    )

    forwards = merge_spans(matches)
    backwards = merge_spans(tuple(reversed(matches)))

    assert forwards == backwards


def test_a_block_overlapping_an_audit_stays_a_block() -> None:
    """Severity is resolved separately from attribution, and severity wins.

    Otherwise a wide ``audit`` rule would be a way to switch off a narrow
    ``block`` one without editing it.
    """
    spans = merge_spans(
        (
            match("watcher", 0, 30, action="audit"),
            match("stopper", 10, 14, action="block"),
        )
    )

    assert len(spans) == 1
    assert spans[0].rule == "watcher"
    assert spans[0].action is GuardrailAction.BLOCK


def test_a_redact_overlapping_an_audit_stays_a_redact() -> None:
    """The same ordering one step down the severity scale."""
    spans = merge_spans(
        (
            match("watcher", 0, 30, action="audit"),
            match("scrubber", 10, 14, action="redact"),
        )
    )

    assert spans[0].action is GuardrailAction.REDACT


def test_adjacent_spans_do_not_merge() -> None:
    """Touching is not overlapping.

    ``[0,5)`` and ``[5,9)`` share no character. Merging them would let two
    unrelated rules be reported as one, and the operator would go looking for a
    single match that never existed.
    """
    spans = merge_spans((match("a", 0, 5), match("b", 5, 9)))

    assert len(spans) == 2
