"""Four of the six scenarios the runtime exists to survive.

Each one is a situation where an unbounded loop misbehaves in a way that is
invisible until it is expensive: it never stops, it spins on the same call, it
outgrows its context, or it loses a whole batch to one bad call. The other two
— a specialist that recurses, and a cancellation arriving while one is in
flight — are properties of sub-agent dispatch and live in
``test_guardrails_subagents``.

These are deliberately pathological. A fixture that is merely realistic proves
the loop works on a good day, which is not the claim Article II makes.
"""

from __future__ import annotations

from collections.abc import Callable
from itertools import count

import pytest

from config.constants.investigation import (
    MAX_INVESTIGATION_LOOPS,
    MAX_STAGNANT_ITERATIONS,
)
from core.agent.react_loop import ReActLoop
from core.agent.runtime_port import RunRequest, RunStatus
from core.agent.session import EvidenceEntry
from core.agent.turn import GuardrailActionKind
from core.capability.metadata import EvidenceType
from core.capability.telemetry import InvocationOutcome
from core.llm.types import ToolCall
from tests.unit.core.agent.conftest import (
    ALWAYS_FAILS,
    DEFAULT_TOOLS,
    LOG_SEARCH,
    METRIC_READ,
    ScriptedLLM,
    call_turn,
    log_call,
    text_turn,
)

pytestmark = pytest.mark.unit


# --- 1. A model that would loop forever ---------------------------------------


def _never_repeats() -> Callable[[object], object]:
    """Return a script that always asks for a call it has never made.

    The stagnation breaker must not be what stops this run: a model that keeps
    finding genuinely new evidence is behaving well and still has to terminate,
    which is the ceiling's job and nothing else's.
    """
    counter = count(1)

    def turn(_: object) -> object:
        index = next(counter)
        return call_turn(log_call(f"c{index}", f"attempt {index}"))

    return turn


async def test_a_model_that_never_concludes_stops_at_the_iteration_ceiling() -> None:
    """SC-001. The script asks for one more, genuinely new, tool call forever."""
    llm = ScriptedLLM(_never_repeats())  # type: ignore[arg-type]
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS)

    result = await loop.run(RunRequest(objective="Why is checkout failing?"))

    assert result.iterations == MAX_INVESTIGATION_LOOPS
    assert result.session.status.is_terminal
    assert any(
        action.kind is GuardrailActionKind.ITERATION_CEILING_REACHED
        for turn in result.turns
        for action in turn.guardrail_actions
    )


async def test_a_caller_may_lower_the_ceiling_but_never_raise_it() -> None:
    llm = ScriptedLLM(_never_repeats())  # type: ignore[arg-type]
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS)

    result = await loop.run(RunRequest(objective="anything", max_iterations=3))

    assert result.iterations == 3


# --- 2. Iterations that produce nothing new -----------------------------------


async def test_duplicate_only_iterations_strip_tool_access_and_force_a_conclusion() -> None:
    """SC-002. Every turn after the first asks for a call already answered."""
    repeated = log_call("c-repeat", "identical every time")
    llm = ScriptedLLM([call_turn(repeated)])
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS)

    result = await loop.run(RunRequest(objective="Why is checkout failing?"))

    nudges = [
        action
        for turn in result.turns
        for action in turn.guardrail_actions
        if action.kind is GuardrailActionKind.STAGNATION_NUDGE
    ]
    stripped = [
        action
        for turn in result.turns
        for action in turn.guardrail_actions
        if action.kind is GuardrailActionKind.TOOL_ACCESS_STRIPPED
    ]

    assert len(nudges) >= MAX_STAGNANT_ITERATIONS
    assert stripped, "tool access is stripped once the stagnation threshold is reached"
    assert result.turns[-1].offered_capabilities == ()
    assert result.iterations < MAX_INVESTIGATION_LOOPS, (
        "the stagnation breaker has to fire before the iteration ceiling, "
        "or it is not doing anything the ceiling was not already doing"
    )


async def test_the_replayed_result_tells_the_model_it_already_has_it() -> None:
    repeated = log_call("c-repeat", "identical every time")
    llm = ScriptedLLM([call_turn(repeated)])
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS)

    result = await loop.run(RunRequest(objective="anything"))

    replayed = [
        execution for turn in result.turns for execution in turn.executions if execution.replayed
    ]
    assert replayed, "the second identical call is served from the in-run cache"

    tool_texts = [
        item.content for message in result.session.transcript for item in message.tool_results
    ]
    assert any("already" in text.lower() for text in tool_texts)


# --- 3. Evidence that outgrows the context ------------------------------------


async def test_a_tight_budget_completes_and_explains_every_drop() -> None:
    """SC-003. Two hundred entries, eight thousand tokens, nothing silent."""
    llm = ScriptedLLM([text_turn("The 12:02 deploy introduced the regression.")])
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS)

    request = RunRequest(objective="Why is checkout failing?", context_budget_tokens=8_000)
    session = loop.new_session(request)
    for index in range(200):
        session.record_evidence(
            EvidenceEntry(
                id=f"e{index}",
                capability="fixture_log_search",
                summary=f"sample {index}",
                evidence_type=EvidenceType.LOG,
                source="fixture",
                content="x" * 2_000,
                iteration=index // 10,
            )
        )

    result = await loop.resume(session)

    assert result.status is RunStatus.COMPLETED
    actions = [action for turn in result.turns for action in turn.budget_actions]
    assert actions, "a run this far over budget cannot have left the evidence untouched"
    assert all(action.reason for action in actions), "every drop names why it was the one to go"
    assert all(action.evidence_id for action in actions)


# --- 5. A parallel batch where one call fails ---------------------------------


async def test_one_failing_call_does_not_take_the_batch_with_it() -> None:
    llm = ScriptedLLM(
        [
            call_turn(
                log_call("c1"),
                ToolCall(id="c2", name="fixture_always_fails", arguments={}),
                ToolCall(
                    id="c3", name="fixture_metric_read", arguments={"series": "checkout.latency"}
                ),
            ),
            text_turn("Two of three reads landed; the deploy is the cause."),
        ],
        repeat_last=False,
    )
    loop = ReActLoop(llm=llm, tools=(LOG_SEARCH, METRIC_READ, ALWAYS_FAILS))

    result = await loop.run(RunRequest(objective="anything"))

    executions = {
        execution.call_id: execution for turn in result.turns for execution in turn.executions
    }
    assert executions["c1"].outcome is InvocationOutcome.SUCCESS
    assert executions["c2"].outcome is InvocationOutcome.FAILURE
    assert executions["c3"].outcome is InvocationOutcome.SUCCESS
    assert result.status is RunStatus.COMPLETED
