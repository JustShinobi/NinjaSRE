"""A resumed session matches its pre-suspension state exactly.

"Exactly" is asserted against the whole record rather than against a handful of
fields, because the way this breaks is a field that was written and never read
— it silently resets on resume, and nobody notices until the accounting is
wrong a week later.

Compaction is here too. It is the one operation allowed to shorten a session,
and the thing it may not shorten is the evidence: a conclusion whose basis was
dropped to save tokens is a conclusion the trace cannot support.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from surfaces.cli.models import CostReport
from surfaces.repl.session import Exchange, ReplSession, SessionStore

pytestmark = pytest.mark.unit


def _populated() -> ReplSession:
    """Return a session with something in every field that has to survive."""
    session = ReplSession(
        session_id="sess-abc123",
        team_node_id="payments",
        started_at=datetime(2026, 3, 14, 9, 0, tzinfo=UTC),
        model_id="claude-sonnet-5",
        effort="high",
        active_run_id="run-0001",
        awaiting=("int-1", "int-2"),
    )
    session.record("human", "checkout latency doubled after the 14:02 deploy")
    session.record("agent", "the connection pool was halved", run_id="run-0001", evidence=("ev-1",))
    session.record("human", "roll it back")
    session.record("agent", "rolled back", run_id="run-0001", evidence=("ev-2", "ev-3"))
    session.spend(CostReport(runs=1, turns=6, prompt_tokens=4200, completion_tokens=900, cost=0.11))
    return session


def test_a_round_trip_preserves_the_whole_record() -> None:
    original = _populated()

    restored = ReplSession.from_record(original.to_record())

    assert restored.to_record() == original.to_record()


def test_the_transcript_survives_intact() -> None:
    original = _populated()

    restored = ReplSession.from_record(original.to_record())

    assert len(restored.transcript) == len(original.transcript)
    for before, after in zip(original.transcript, restored.transcript):
        assert after == before


def test_the_accounting_survives_intact() -> None:
    original = _populated()

    restored = ReplSession.from_record(original.to_record())

    assert restored.cost == original.cost
    assert restored.cost.total_tokens == 5100


def test_the_evidence_references_survive_intact() -> None:
    original = _populated()

    restored = ReplSession.from_record(original.to_record())

    assert restored.evidence_ids == ("ev-1", "ev-2", "ev-3")


def test_what_the_run_was_waiting_on_survives() -> None:
    # The field most easily forgotten, and the one that leaves a resumed session
    # unable to say which question is still open.
    original = _populated()

    restored = ReplSession.from_record(original.to_record())

    assert restored.awaiting == ("int-1", "int-2")


def test_every_written_field_is_read_back() -> None:
    # The structural assertion behind "exactly". A field in the record that
    # ``from_record`` ignores resets silently on resume.
    written = set(_populated().to_record())
    round_tripped = set(ReplSession.from_record(_populated().to_record()).to_record())

    assert written == round_tripped


def test_a_session_survives_a_trip_through_the_filesystem(tmp_path: Path) -> None:
    store = SessionStore(directory=tmp_path / "sessions")
    original = _populated()

    store.save(original)
    restored = store.load(original.session_id)

    assert restored is not None
    assert restored.to_record() == original.to_record()


def test_loading_a_session_that_does_not_exist_returns_nothing(tmp_path: Path) -> None:
    store = SessionStore(directory=tmp_path / "sessions")

    assert store.load("never-existed") is None


def test_sessions_list_most_recently_updated_first(tmp_path: Path) -> None:
    store = SessionStore(directory=tmp_path / "sessions")
    older = ReplSession(session_id="old", updated_at=datetime(2026, 3, 1, tzinfo=UTC))
    newer = ReplSession(session_id="new", updated_at=datetime(2026, 3, 14, tzinfo=UTC))
    store.save(older)
    store.save(newer)

    listed = store.list_sessions()

    assert [session.session_id for session in listed] == ["new", "old"]


def test_one_unreadable_session_does_not_hide_the_others(tmp_path: Path) -> None:
    # "No sessions" would be a lie about the ones that are fine.
    store = SessionStore(directory=tmp_path / "sessions")
    store.save(ReplSession(session_id="good"))
    (tmp_path / "sessions" / "broken.json").write_text("{not json", encoding="utf-8")

    listed = store.list_sessions()

    assert [session.session_id for session in listed] == ["good"]


def test_compaction_drops_exchanges_and_keeps_every_evidence_reference() -> None:
    session = ReplSession(session_id="sess-1")
    for index in range(20):
        session.record("agent", f"turn {index}", evidence=(f"ev-{index}",))
    before = set(session.evidence_ids)

    dropped = session.compact(keep=5)

    assert dropped == 15
    assert len(session.transcript) == 5
    assert set(session.evidence_ids) == before, "compaction lost evidence references"


def test_compaction_below_the_threshold_changes_nothing() -> None:
    session = ReplSession(session_id="sess-1")
    session.record("human", "one thing")

    assert session.compact(keep=10) == 0
    assert len(session.transcript) == 1


def test_a_compacted_session_still_round_trips() -> None:
    session = _populated()
    session.compact(keep=2)

    restored = ReplSession.from_record(session.to_record())

    assert restored.to_record() == session.to_record()
    assert restored.evidence_ids == ("ev-1", "ev-2", "ev-3")


def test_the_first_thing_a_person_said_becomes_the_objective() -> None:
    # What a listing shows. "session 4f2a" is not something anybody recognises.
    session = ReplSession(session_id="sess-1")
    session.record("agent", "starting")
    session.record("human", "checkout is slow")
    session.record("human", "and payments too")

    assert session.objective == "checkout is slow"


def test_a_summary_reports_what_a_listing_needs() -> None:
    summary = _populated().summary()

    assert summary.session_id == "sess-abc123"
    assert summary.turns == 4
    assert summary.evidence == 3
    assert summary.awaiting == "int-1, int-2"


def test_an_exchange_round_trips_on_its_own() -> None:
    exchange = Exchange(
        speaker="agent",
        text="the pool was halved",
        at=datetime(2026, 3, 14, 9, 5, tzinfo=UTC),
        run_id="run-0001",
        evidence_ids=("ev-1",),
    )

    assert Exchange.from_record(exchange.to_record()) == exchange


def test_deleting_a_session_reports_whether_one_went(tmp_path: Path) -> None:
    store = SessionStore(directory=tmp_path / "sessions")
    store.save(ReplSession(session_id="sess-1"))

    assert store.delete("sess-1") is True
    assert store.delete("sess-1") is False
