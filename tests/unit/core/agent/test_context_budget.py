"""What gets dropped when the evidence outgrows the window, and why that one.

The policy has to be explainable. "The context filled up and something went" is
what an operator reads when a conclusion is missing the observation that would
have supported it, and it is not an answer. So the value function is four named
terms, the ordering it produces is pinned by a golden test, and every drop
carries the sentence that says why it was the one to go.
"""

from __future__ import annotations

import pytest

from core.agent.context_budget import BudgetPolicy, apply_budget, evidence_value
from core.agent.session import EvidenceEntry, Session
from core.agent.turn import BudgetActionKind
from core.capability.metadata import EvidenceType
from core.llm.types import Message, Role, ToolResult

pytestmark = pytest.mark.unit


def _entry(
    identifier: str,
    *,
    iteration: int = 0,
    content: str = "x" * 400,
    cited: bool = False,
    source: str = "datadog",
    call_id: str = "",
) -> EvidenceEntry:
    return EvidenceEntry(
        id=identifier,
        capability="fixture_log_search",
        summary=f"summary {identifier}",
        evidence_type=EvidenceType.LOG,
        source=source,
        content=content,
        iteration=iteration,
        cited=cited,
        call_id=call_id,
    )


# --- the value function -------------------------------------------------------


def test_recent_evidence_outranks_old_evidence_of_the_same_size() -> None:
    old = evidence_value(_entry("a", iteration=0), current_iteration=10, largest_tokens=100)
    new = evidence_value(_entry("b", iteration=9), current_iteration=10, largest_tokens=100)

    assert new > old


def test_cited_evidence_outranks_uncited_evidence_of_the_same_age() -> None:
    """An entry a prior turn reasoned from is one the model will reach for
    again; evicting it is how a run forgets its own argument."""
    plain = evidence_value(_entry("a", iteration=5), current_iteration=10, largest_tokens=100)
    cited = evidence_value(
        _entry("b", iteration=5, cited=True), current_iteration=10, largest_tokens=100
    )

    assert cited > plain


def test_a_large_entry_ranks_below_a_small_one_of_the_same_age() -> None:
    small = _entry("a", iteration=5, content="x" * 100)
    large = _entry("b", iteration=5, content="x" * 8_000)
    largest = large.tokens

    assert evidence_value(small, current_iteration=10, largest_tokens=largest) > evidence_value(
        large, current_iteration=10, largest_tokens=largest
    )


def test_the_agents_own_reasoning_ranks_below_a_measurement() -> None:
    measured = _entry("a", iteration=5, source="datadog")
    reasoned = _entry("b", iteration=5, source="reasoning")

    assert evidence_value(measured, current_iteration=10, largest_tokens=100) > evidence_value(
        reasoned, current_iteration=10, largest_tokens=100
    )


# --- the golden ordering ------------------------------------------------------


def test_the_eviction_order_is_pinned() -> None:
    """T011. This ordering is the policy. Changing it is a deliberate retune,
    and it should show up here as a diff rather than as a scenario score that
    moved for reasons nobody can name."""
    entries = (
        _entry("oldest-small", iteration=0, content="x" * 200),
        _entry("oldest-large", iteration=0, content="x" * 8_000),
        _entry("recent-small", iteration=9, content="x" * 200),
        _entry("recent-large", iteration=9, content="x" * 8_000),
        _entry("old-cited", iteration=0, content="x" * 8_000, cited=True),
        _entry("recent-reasoning", iteration=9, content="x" * 200, source="reasoning"),
    )
    largest = max(entry.tokens for entry in entries)

    ordered = sorted(
        entries,
        key=lambda entry: evidence_value(entry, current_iteration=10, largest_tokens=largest),
    )

    assert [entry.id for entry in ordered] == [
        # Big and stale: the cheapest thing to lose and the least likely to be
        # reached for again.
        "oldest-large",
        # Recent, but the agent's own prose. It can restate a hypothesis; it
        # cannot re-observe a log line from four hours ago. Provenance beats
        # size here on purpose — the reliability penalty exceeds the largest
        # size penalty a single entry can carry.
        "recent-reasoning",
        # Recent and measured, but as large as anything held.
        "recent-large",
        "oldest-small",
        "recent-small",
        # Cited: the backbone of an argument the run is still making.
        "old-cited",
    ]


# --- applying the budget ------------------------------------------------------


def test_a_session_within_budget_is_left_alone() -> None:
    session = Session(id="run-1")
    session.record_evidence(_entry("e1", content="x" * 100))

    actions = apply_budget(session, BudgetPolicy(total_tokens=100_000))

    assert actions == ()
    assert session.evidence[0].content == "x" * 100


def test_truncation_comes_before_eviction() -> None:
    session = Session(id="run-1")
    for index in range(20):
        session.record_evidence(_entry(f"e{index}", iteration=index, content="x" * 2_000))
    session.iteration = 20

    actions = apply_budget(session, BudgetPolicy(total_tokens=4_000))

    kinds = {action.kind for action in actions}
    assert BudgetActionKind.TRUNCATED in kinds


def test_every_action_names_the_entry_and_the_reason() -> None:
    session = Session(id="run-1")
    for index in range(50):
        session.record_evidence(_entry(f"e{index}", iteration=index, content="x" * 2_000))
    session.iteration = 50

    actions = apply_budget(session, BudgetPolicy(total_tokens=2_000))

    assert actions
    for action in actions:
        assert action.evidence_id
        assert action.reason
        assert action.tokens_before >= action.tokens_after


def test_an_evicted_entry_keeps_its_summary_and_reference() -> None:
    """Article I: a reference is what makes a claim checkable. Dropping the
    body to fit is a budget decision; dropping the pointer is data loss."""
    session = Session(id="run-1")
    for index in range(40):
        session.record_evidence(_entry(f"e{index}", iteration=index, content="x" * 4_000))
    session.iteration = 40

    apply_budget(session, BudgetPolicy(total_tokens=1_000))

    assert len(session.evidence) == 40
    assert all(entry.summary for entry in session.evidence)


def test_the_budget_rewrites_the_transcript_the_model_actually_reads() -> None:
    """Trimming the evidence record while the transcript still carries the full
    payload would leave the budget enforcing nothing at all."""
    session = Session(id="run-1")
    for index in range(30):
        call_id = f"c{index}"
        session.record_evidence(
            _entry(f"e{index}", iteration=index, content="x" * 4_000, call_id=call_id)
        )
        session.append(
            Message(
                role=Role.TOOL,
                tool_results=(
                    ToolResult(call_id=call_id, name="fixture_log_search", content="x" * 4_000),
                ),
            )
        )
    session.iteration = 30

    apply_budget(session, BudgetPolicy(total_tokens=2_000))

    transcript_chars = sum(
        len(result.content) for message in session.transcript for result in message.tool_results
    )
    assert transcript_chars < 30 * 4_000


def test_the_most_valuable_evidence_survives_a_tight_budget() -> None:
    session = Session(id="run-1")
    for index in range(30):
        session.record_evidence(_entry(f"e{index}", iteration=index, content="x" * 2_000))
    session.record_evidence(_entry("keeper", iteration=29, content="x" * 2_000, cited=True))
    session.iteration = 30

    apply_budget(session, BudgetPolicy(total_tokens=3_000))

    keeper = session.find_evidence("keeper")
    assert keeper is not None
    assert keeper.content, "the cited, most recent entry is the last thing to go"


def test_a_budget_too_small_for_anything_still_completes() -> None:
    """The edge case in the spec: a budget so tight that the system prompt plus
    one entry exceeds it. The loop must still be able to make a call."""
    session = Session(id="run-1")
    for index in range(10):
        session.record_evidence(_entry(f"e{index}", iteration=index, content="x" * 4_000))
    session.iteration = 10

    actions = apply_budget(session, BudgetPolicy(total_tokens=1))

    assert actions
    assert all(entry.content == "" for entry in session.evidence)


def test_a_zero_budget_means_no_budget_rather_than_no_room() -> None:
    """Zero is how a caller says "use the model's window"; reading it as a
    literal ceiling would evict everything on every run."""
    session = Session(id="run-1")
    session.record_evidence(_entry("e1", content="x" * 40_000))

    assert apply_budget(session, BudgetPolicy(total_tokens=0)) == ()
