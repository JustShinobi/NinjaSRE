"""The two guardrail scenarios that only exist once specialists do.

Split from ``test_guardrails`` because these are the same six-scenario set:
a specialist that would recurse forever, and a cancellation that arrives while
one is in flight. Both are properties of sub-agent dispatch rather than of the
loop's own control flow, and both fail in ways nothing else in the suite would
notice.
"""

from __future__ import annotations

import asyncio

import pytest

from config.constants.investigation import MAX_SUBAGENT_DEPTH
from core.agent.react_loop import ReActLoop
from core.agent.runtime_port import RunRequest, RunStatus
from core.agent.session import Session, SessionStatus
from core.agent.subagents.definition import SubAgent
from core.agent.subagents.dispatch import SubAgentRun
from core.agent.subagents.findings import Finding
from core.agent.turn import GuardrailActionKind
from core.llm.types import ToolCall
from tests.unit.core.agent.conftest import (
    DEFAULT_TOOLS,
    ScriptedLLM,
    call_turn,
    text_turn,
)

pytestmark = pytest.mark.unit


# --- 4. A specialist that would recurse ---------------------------------------


async def test_a_subagent_may_not_dispatch_past_the_depth_bound() -> None:
    recursive = SubAgent(
        name="recursive-analyst",
        description="Dispatches another copy of itself, given the chance.",
        capabilities=("fixture_log_search",),
        max_iterations=2,
    )
    llm = ScriptedLLM(
        [
            call_turn(
                ToolCall(
                    id="d1",
                    name="dispatch_subagent",
                    arguments={"subagent": "recursive-analyst", "task": "go deeper"},
                )
            )
        ]
    )
    loop = ReActLoop(llm=llm, tools=DEFAULT_TOOLS, subagents=(recursive,))

    result = await loop.run(RunRequest(objective="anything", max_iterations=6))

    refusals = [
        action
        for turn in result.turns
        for action in turn.guardrail_actions
        if action.kind is GuardrailActionKind.SUBAGENT_DEPTH_EXCEEDED
    ]
    assert refusals, f"nesting was never refused within {MAX_SUBAGENT_DEPTH} levels"


# --- 6. Cancellation while a specialist is in flight --------------------------


async def test_cancelling_mid_subagent_leaves_a_resumable_session() -> None:
    """SC-006. The loop stops at the next safe point, not in the middle of one."""
    started = asyncio.Event()
    release = asyncio.Event()

    slow = SubAgent(
        name="slow-analyst",
        description="Blocks until the test lets it go.",
        capabilities=("fixture_log_search",),
        max_iterations=2,
    )

    llm = ScriptedLLM(
        [
            call_turn(
                ToolCall(
                    id="d1",
                    name="dispatch_subagent",
                    arguments={"subagent": "slow-analyst", "task": "look at the logs"},
                )
            ),
            text_turn("Cancelled before a conclusion."),
        ],
        repeat_last=False,
    )

    async def blocking_child(definition: SubAgent, task: str, parent: Session) -> SubAgentRun:
        started.set()
        await release.wait()
        return SubAgentRun(finding=Finding(subagent=definition.name, headline="the logs are quiet"))

    loop = ReActLoop(
        llm=llm,
        tools=DEFAULT_TOOLS,
        subagents=(slow,),
        subagent_runner=blocking_child,
    )

    request = RunRequest(objective="anything")
    session = loop.new_session(request)
    running = asyncio.create_task(loop.resume(session))

    await asyncio.wait_for(started.wait(), timeout=2.0)
    await loop.cancel(session.id)
    release.set()

    result = await asyncio.wait_for(running, timeout=2.0)

    assert result.status is RunStatus.CANCELLED
    assert result.session.status is SessionStatus.CANCELLED
    restored = Session.from_record(result.session.to_record())
    assert restored.id == session.id
    assert restored.status is SessionStatus.CANCELLED
    assert restored.evidence, "the finding the specialist did produce survived the cancellation"
