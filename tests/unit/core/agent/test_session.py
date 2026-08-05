"""A session is the run's memory, and it has to survive being written down.

Resumption is not a nice-to-have here: an investigation that is cancelled
mid-sub-agent has to come back coherent, and a trace that cannot be replayed
offline is a summary rather than evidence. Both properties reduce to the same
one — everything the loop holds round-trips through a record and comes back
identical.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.agent.session import EvidenceEntry, Session, SessionStatus
from core.capability.metadata import EvidenceType
from core.llm.types import Message, Role, ToolCall, ToolResult

pytestmark = pytest.mark.unit


def _entry(identifier: str = "", **overrides: object) -> EvidenceEntry:
    fields: dict[str, object] = {
        "id": identifier,
        "capability": "datadog_log_statistics",
        "summary": "412 errors in the checkout service",
        "evidence_type": EvidenceType.LOG,
        "source": "datadog",
        "content": "status=500 count=412",
        "reference": "query:abc123",
    }
    fields.update(overrides)
    return EvidenceEntry(**fields)  # type: ignore[arg-type]


def test_a_new_session_is_running_and_empty() -> None:
    session = Session(id="run-1", objective="Why is checkout failing?")

    assert session.status is SessionStatus.RUNNING
    assert session.iteration == 0
    assert session.transcript == []
    assert session.evidence == []


def test_recording_evidence_assigns_a_stable_identifier() -> None:
    session = Session(id="run-1")

    first = session.record_evidence(_entry())
    second = session.record_evidence(_entry())

    assert first.id
    assert second.id
    assert first.id != second.id
    assert [entry.id for entry in session.evidence] == [first.id, second.id]


def test_a_supplied_evidence_identifier_is_kept() -> None:
    """A sub-agent's finding arrives already identified; renumbering it would
    break the provenance the parent recorded against."""
    session = Session(id="run-1")

    stored = session.record_evidence(_entry("finding-log-analyst-1"))

    assert stored.id == "finding-log-analyst-1"


def test_citing_evidence_marks_the_stored_entry() -> None:
    session = Session(id="run-1")
    stored = session.record_evidence(_entry())

    session.cite(stored.id)

    assert session.evidence[0].cited is True


def test_citing_an_unknown_identifier_is_refused() -> None:
    session = Session(id="run-1")

    with pytest.raises(KeyError):
        session.cite("nothing-recorded-under-this")


def test_evidence_tokens_are_measured_from_what_the_model_reads() -> None:
    small = _entry(content="a")
    large = _entry(content="a" * 4_000)

    assert large.tokens > small.tokens


def test_a_session_round_trips_through_a_record() -> None:
    session = Session(
        id="run-1",
        objective="Why is checkout failing?",
        system_prompt="You investigate incidents.",
        alert_source="datadog",
        depth=1,
        context={"team": "payments"},
    )
    session.append(Message(role=Role.USER, text="Checkout is returning 500s."))
    session.append(
        Message(
            role=Role.ASSISTANT,
            text="Checking the logs.",
            tool_calls=(ToolCall(id="c1", name="datadog_log_statistics", arguments={"q": "x"}),),
        )
    )
    session.append(
        Message(
            role=Role.TOOL,
            tool_results=(ToolResult(call_id="c1", name="datadog_log_statistics", content="412"),),
        )
    )
    stored = session.record_evidence(_entry())
    session.cite(stored.id)
    session.iteration = 3
    session.stagnant_iterations = 1
    session.tools_stripped = True
    session.status = SessionStatus.SUSPENDED

    restored = Session.from_record(session.to_record())

    assert restored.id == session.id
    assert restored.objective == session.objective
    assert restored.system_prompt == session.system_prompt
    assert restored.alert_source == session.alert_source
    assert restored.depth == 1
    assert restored.context == {"team": "payments"}
    assert restored.iteration == 3
    assert restored.stagnant_iterations == 1
    assert restored.tools_stripped is True
    assert restored.status is SessionStatus.SUSPENDED
    assert restored.transcript == session.transcript
    assert restored.evidence == session.evidence


def test_a_record_survives_json() -> None:
    """The trace store speaks JSON; anything that does not survive it is not
    in the trace however carefully it was collected."""
    import json

    session = Session(id="run-1", objective="Why is checkout failing?")
    session.append(Message(role=Role.USER, text="Checkout is returning 500s."))
    session.record_evidence(_entry())

    restored = Session.from_record(json.loads(json.dumps(session.to_record())))

    assert restored.transcript == session.transcript
    assert restored.evidence == session.evidence


def test_terminal_statuses_are_named_rather_than_listed_at_call_sites() -> None:
    assert SessionStatus.COMPLETED.is_terminal
    assert SessionStatus.CANCELLED.is_terminal
    assert SessionStatus.FAILED.is_terminal
    assert not SessionStatus.RUNNING.is_terminal
    assert not SessionStatus.SUSPENDED.is_terminal


def test_touching_a_session_moves_its_update_time_forward() -> None:
    session = Session(id="run-1", updated_at=datetime(2020, 1, 1, tzinfo=UTC))

    session.append(Message(role=Role.USER, text="anything"))

    assert session.updated_at > datetime(2020, 1, 1, tzinfo=UTC)
