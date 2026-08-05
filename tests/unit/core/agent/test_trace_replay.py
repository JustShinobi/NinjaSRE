"""SC-008. A run reconstructed from its stored trace alone.

The standard is not "enough to debug with". It is that someone holding only the
serialised turns — no session object, no transcript, no live process — can say
what the run did: which capabilities were on each turn, what the model asked
for, what came back, what the budget dropped, and what a guardrail did about it.

The test does the reconstruction from JSON rather than from the objects, because
the objects are what a live process has and JSON is what a store returns.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from core.agent.react_loop import ReActLoop
from core.agent.runtime_port import RunRequest
from core.agent.session import EvidenceEntry, Session
from core.agent.turn import Turn
from core.capability.metadata import EvidenceType
from core.capability.telemetry import InvocationOutcome
from core.llm.types import ToolCall
from tests.unit.core.agent.conftest import (
    DEFAULT_TOOLS,
    ScriptedLLM,
    call_turn,
    log_call,
    text_turn,
)

pytestmark = pytest.mark.unit


async def _recorded_run() -> tuple[list[dict[str, Any]], Session]:
    """Run something with every kind of event in it, and return its stored turns."""
    llm = ScriptedLLM(
        [
            call_turn(log_call("c1"), text="Starting with the logs."),
            call_turn(
                log_call("c2", "different query"),
                ToolCall(id="c3", name="fixture_always_fails", arguments={}),
                ToolCall(id="c4", name="fixture_invented", arguments={}),
                text="Widening the search.",
            ),
            call_turn(log_call("c5"), text="Re-checking the first query."),
            text_turn("The 12:02 deploy introduced the regression."),
        ],
        repeat_last=False,
    )
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS)

    session = loop.new_session(
        RunRequest(objective="Why is checkout failing?", context_budget_tokens=2_000)
    )
    for index in range(30):
        session.record_evidence(
            EvidenceEntry(
                id=f"seed{index}",
                capability="fixture_log_search",
                summary=f"prior sample {index}",
                evidence_type=EvidenceType.LOG,
                source="fixture",
                content="x" * 3_000,
                iteration=0,
            )
        )

    result = await loop.resume(session)
    stored = json.loads(json.dumps([turn.to_record() for turn in result.turns]))
    return stored, result.session


async def test_the_stored_turns_survive_json_unchanged() -> None:
    stored, session = await _recorded_run()

    assert [Turn.from_record(record) for record in stored] == session.turns


async def test_the_sequence_of_calls_is_recoverable_from_the_trace_alone() -> None:
    stored, _ = await _recorded_run()

    replayed = [
        (record["index"], execution["capability"], execution["arguments"])
        for record in stored
        for execution in record["executions"]
    ]

    assert replayed[0] == (1, "fixture_log_search", {"query": "service:checkout status:500"})
    assert [name for _, name, _ in replayed].count("fixture_always_fails") == 1
    assert "fixture_invented" in [name for _, name, _ in replayed]


async def test_what_was_offered_is_recoverable_even_where_nothing_was_called() -> None:
    """ "It never considered the metrics tool" and "the metrics tool was not on
    the turn" have opposite fixes, and only one of them is a prompt problem."""
    stored, _ = await _recorded_run()

    assert stored[0]["offered_capabilities"] == sorted(tool.name for tool in DEFAULT_TOOLS)
    assert stored[-1]["executions"] == []
    assert stored[-1]["offered_capabilities"]


async def test_every_outcome_is_recoverable_including_the_failures() -> None:
    stored, _ = await _recorded_run()

    outcomes = {
        execution["call_id"]: execution for record in stored for execution in record["executions"]
    }
    assert outcomes["c1"]["outcome"] == InvocationOutcome.SUCCESS.value
    assert outcomes["c3"]["outcome"] == InvocationOutcome.FAILURE.value
    assert outcomes["c3"]["error_class"] == "upstream_error"
    assert outcomes["c4"]["denied"] is True
    assert outcomes["c5"]["replayed"] is True


async def test_every_budget_action_is_recoverable_with_its_reason() -> None:
    stored, _ = await _recorded_run()

    actions = [action for record in stored for action in record["budget_actions"]]

    assert actions, "the run was over budget; the trace has to say what went"
    for action in actions:
        assert action["evidence_id"]
        assert action["reason"]
        assert action["kind"] in {"evicted", "truncated"}


async def test_every_guardrail_action_is_recoverable() -> None:
    stored, _ = await _recorded_run()

    kinds = {action["kind"] for record in stored for action in record["guardrail_actions"]}

    assert "replayed_duplicate" in kinds
    assert "unknown_capability" in kinds


async def test_the_accounting_is_recoverable_per_turn() -> None:
    stored, _ = await _recorded_run()

    priced = [record["usage"] for record in stored if record["usage"]]

    assert priced
    assert all(record["tokens"]["input_tokens"] > 0 for record in priced)


async def test_the_whole_session_replays_from_one_record() -> None:
    _, session = await _recorded_run()

    restored = Session.from_record(json.loads(json.dumps(session.to_record())))

    assert restored.turns == session.turns
    assert restored.evidence == session.evidence
    assert restored.transcript == session.transcript
    assert restored.usage.tokens == session.usage.tokens
