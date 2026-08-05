"""Hooks as the loop actually uses them.

``test_hooks`` covers dispatch in isolation. This is the other question: does a
denial reach the model in a form it can act on, does a rewrite reach the tool,
and does a broken hook still leave a completed turn behind?
"""

from __future__ import annotations

import pytest

from core.agent.hooks.builtin import default_hooks
from core.agent.hooks.registry import HookRegistry
from core.agent.hooks.types import Deny, HookPoint, Rewrite, ToolContext
from core.agent.react_loop import ReActLoop
from core.agent.runtime_port import RunRequest, RunStatus
from core.agent.session import Session
from core.agent.turn import GuardrailActionKind, Turn
from core.capability.result import CapabilityErrorClass, CapabilityResult
from core.capability.telemetry import InvocationOutcome
from core.llm.types import ToolCall
from tests.unit.core.agent.conftest import (
    DEFAULT_TOOLS,
    LOG_SEARCH,
    ScriptedLLM,
    call_turn,
    log_call,
    text_turn,
)

pytestmark = pytest.mark.unit


def _two_turn_script() -> ScriptedLLM:
    return ScriptedLLM([call_turn(log_call("c1")), text_turn("Understood.")], repeat_last=False)


# --- denial (T021) -------------------------------------------------------------


async def test_a_denied_call_comes_back_to_the_model_as_a_structured_result() -> None:
    hooks = HookRegistry()

    async def refuse(call: ToolCall, context: ToolContext) -> Deny:
        return Deny(reason="A human has to approve reads against production logs.")

    hooks.register(HookPoint.PRE_TOOL_USE, refuse, name="approvals")
    loop = ReActLoop(llm=_two_turn_script(), tools=DEFAULT_TOOLS, hooks=hooks)

    result = await loop.run(RunRequest(objective="anything"))

    execution = result.turns[0].executions[0]
    assert execution.denied
    assert execution.outcome is InvocationOutcome.FAILURE
    assert execution.error_class is CapabilityErrorClass.APPROVAL_REQUIRED

    replies = [
        item.content for message in result.session.transcript for item in message.tool_results
    ]
    assert any("A human has to approve" in reply for reply in replies)


async def test_a_denied_call_is_recorded_as_a_guardrail_action() -> None:
    hooks = HookRegistry()

    async def refuse(call: ToolCall, context: ToolContext) -> Deny:
        return Deny(
            reason="blocked by policy", classification=CapabilityErrorClass.PERMISSION_DENIED
        )

    hooks.register(HookPoint.PRE_TOOL_USE, refuse, name="guardrails")
    loop = ReActLoop(llm=_two_turn_script(), tools=DEFAULT_TOOLS, hooks=hooks)

    result = await loop.run(RunRequest(objective="anything"))

    assert any(
        action.kind is GuardrailActionKind.CALL_DENIED
        for turn in result.turns
        for action in turn.guardrail_actions
    )


async def test_a_denied_call_never_runs_the_tool() -> None:
    ran: list[str] = []
    hooks = HookRegistry()

    async def refuse(call: ToolCall, context: ToolContext) -> Deny:
        return Deny(reason="not allowed")

    async def witness(call: ToolCall, result: CapabilityResult, context: ToolContext) -> None:
        ran.append(call.name)

    hooks.register(HookPoint.PRE_TOOL_USE, refuse, name="deny")
    hooks.register(HookPoint.POST_TOOL_USE, witness, name="witness")
    loop = ReActLoop(llm=_two_turn_script(), tools=DEFAULT_TOOLS, hooks=hooks)

    await loop.run(RunRequest(objective="anything"))

    assert ran == [], "post_tool_use cannot fire for a call that never happened"


# --- rewrite (T022) ------------------------------------------------------------


async def test_a_rewrite_reaches_the_tool_that_runs() -> None:
    """Masking is exactly this: the value the model sent never reaches the
    vendor, and nothing above the hook holds the original."""
    hooks = HookRegistry()

    async def mask(call: ToolCall, context: ToolContext) -> Rewrite:
        return Rewrite(arguments={"query": "MASKED"}, reason="credential-shaped argument")

    hooks.register(HookPoint.PRE_TOOL_USE, mask, name="masking")
    loop = ReActLoop(llm=_two_turn_script(), tools=DEFAULT_TOOLS, hooks=hooks)

    result = await loop.run(RunRequest(objective="anything"))

    replies = [
        item.content for message in result.session.transcript for item in message.tool_results
    ]
    assert any("MASKED" in reply for reply in replies)
    assert any(
        action.kind is GuardrailActionKind.ARGUMENTS_REWRITTEN
        for turn in result.turns
        for action in turn.guardrail_actions
    )


async def test_post_tool_use_filtering_reaches_the_transcript() -> None:
    hooks = HookRegistry()

    async def redact(
        call: ToolCall, result: CapabilityResult, context: ToolContext
    ) -> CapabilityResult:
        return CapabilityResult.ok(result.capability, value="[filtered by guardrails]")

    hooks.register(HookPoint.POST_TOOL_USE, redact, name="output-filter")
    loop = ReActLoop(llm=_two_turn_script(), tools=DEFAULT_TOOLS, hooks=hooks)

    result = await loop.run(RunRequest(objective="anything"))

    replies = [
        item.content for message in result.session.transcript for item in message.tool_results
    ]
    assert any("[filtered by guardrails]" in reply for reply in replies)


# --- failures (T026) -----------------------------------------------------------


async def test_a_raising_hook_is_recorded_and_the_turn_still_completes() -> None:
    hooks = HookRegistry()

    async def broken(session: Session, turn: Turn) -> None:
        raise RuntimeError("the accounting sink is down")

    hooks.register(HookPoint.ON_TURN_END, broken, name="broken-accounting")
    loop = ReActLoop(llm=_two_turn_script(), tools=DEFAULT_TOOLS, hooks=hooks)

    result = await loop.run(RunRequest(objective="anything"))

    assert result.status is RunStatus.COMPLETED
    failures = [failure for turn in result.turns for failure in turn.hook_failures]
    assert [failure.hook for failure in failures] == ["broken-accounting"] * len(result.turns)
    assert "the accounting sink is down" in failures[0].error


async def test_a_run_level_hook_failure_is_on_the_result() -> None:
    hooks = HookRegistry()

    async def broken(session: Session) -> None:
        raise RuntimeError("memory recall is unreachable")

    hooks.register(HookPoint.ON_RUN_START, broken, name="memory-recall")
    loop = ReActLoop(llm=ScriptedLLM([text_turn("done")]), tools=DEFAULT_TOOLS, hooks=hooks)

    result = await loop.run(RunRequest(objective="anything"))

    assert result.status is RunStatus.COMPLETED
    assert [failure.hook for failure in result.hook_failures] == ["memory-recall"]


async def test_a_broken_pre_tool_use_hook_does_not_block_the_call() -> None:
    hooks = HookRegistry()

    async def broken(call: ToolCall, context: ToolContext) -> None:
        raise RuntimeError("the masking rules failed to load")

    hooks.register(HookPoint.PRE_TOOL_USE, broken, name="masking")
    loop = ReActLoop(llm=_two_turn_script(), tools=DEFAULT_TOOLS, hooks=hooks)

    result = await loop.run(RunRequest(objective="anything"))

    execution = result.turns[0].executions[0]
    assert not execution.denied
    assert execution.outcome is InvocationOutcome.SUCCESS


# --- lifecycle coverage --------------------------------------------------------


async def test_every_lifecycle_point_fires_over_one_completed_run() -> None:
    seen: list[str] = []
    hooks = HookRegistry()

    async def at_run_start(session: Session) -> None:
        seen.append("on_run_start")

    async def at_pre(call: ToolCall, context: ToolContext) -> None:
        seen.append("pre_tool_use")

    async def at_post(call: ToolCall, result: CapabilityResult, context: ToolContext) -> None:
        seen.append("post_tool_use")

    async def at_turn_end(session: Session, turn: Turn) -> None:
        seen.append("on_turn_end")

    async def at_run_end(session: Session, result: object) -> None:
        seen.append("on_run_end")

    hooks.register(HookPoint.ON_RUN_START, at_run_start, name="s")
    hooks.register(HookPoint.PRE_TOOL_USE, at_pre, name="p")
    hooks.register(HookPoint.POST_TOOL_USE, at_post, name="q")
    hooks.register(HookPoint.ON_TURN_END, at_turn_end, name="t")
    hooks.register(HookPoint.ON_RUN_END, at_run_end, name="r")

    loop = ReActLoop(llm=_two_turn_script(), tools=DEFAULT_TOOLS, hooks=hooks)
    await loop.run(RunRequest(objective="anything"))

    assert seen[0] == "on_run_start"
    assert seen[-1] == "on_run_end"
    assert "pre_tool_use" in seen
    assert "post_tool_use" in seen
    assert seen.count("on_turn_end") == 2


async def test_cancel_fires_on_cancel_and_on_run_end() -> None:
    """A hook that persists state has to run whichever way the run ended; one
    that reaps in-flight work only cares about the cancellation."""
    seen: list[str] = []
    hooks = HookRegistry()

    async def at_cancel(session: Session) -> None:
        seen.append("on_cancel")

    async def at_run_end(session: Session, result: object) -> None:
        seen.append("on_run_end")

    hooks.register(HookPoint.ON_CANCEL, at_cancel, name="c")
    hooks.register(HookPoint.ON_RUN_END, at_run_end, name="r")

    loop = ReActLoop(llm=ScriptedLLM([text_turn("done")]), tools=DEFAULT_TOOLS, hooks=hooks)
    request = RunRequest(objective="anything")
    session = loop.new_session(request)
    await loop.cancel(session.id)

    result = await loop.resume(session)

    assert result.status is RunStatus.CANCELLED
    assert seen == ["on_cancel", "on_run_end"]


# --- the built-in set ----------------------------------------------------------


def test_the_default_hooks_are_observe_only() -> None:
    """A default deployment has exactly one place a call can be refused, and it
    is not the built-in set."""
    hooks = default_hooks()

    assert [hook.name for hook in hooks.hooks_at(HookPoint.PRE_TOOL_USE)] == ["tracing"]
    assert [hook.name for hook in hooks.hooks_at(HookPoint.ON_TURN_END)] == [
        "tracing",
        "accounting",
        "budget",
    ]


async def test_the_default_hooks_survive_a_whole_run() -> None:
    loop = ReActLoop(llm=_two_turn_script(), tools=(LOG_SEARCH,), hooks=default_hooks())

    result = await loop.run(RunRequest(objective="anything", context_budget_tokens=4_000))

    assert result.status is RunStatus.COMPLETED
    assert [failure for turn in result.turns for failure in turn.hook_failures] == []
    assert result.hook_failures == ()
