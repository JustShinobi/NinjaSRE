"""Ordered dispatch, one point that can change control flow, and no exceptions.

Hooks are where masking, approval gating, and memory attach to the loop without
the loop knowing they exist. That only works if two properties hold: a hook that
raises does not take the turn with it, and exactly one point — ``pre_tool_use``
— can alter what happens next. Every other point observes.
"""

from __future__ import annotations

import pytest

from core.agent.hooks.registry import HookRegistry
from core.agent.hooks.types import (
    Allow,
    Deny,
    HookPoint,
    Rewrite,
    ToolContext,
)
from core.agent.session import Session
from core.agent.turn import Turn
from core.capability.result import CapabilityErrorClass, CapabilityResult
from core.llm.types import ToolCall
from tests.unit.core.agent.conftest import LOG_SEARCH

pytestmark = pytest.mark.unit


def _context(session: Session | None = None) -> ToolContext:
    return ToolContext(session=session or Session(id="run-1"), iteration=1, registered=LOG_SEARCH)


def _call(**arguments: object) -> ToolCall:
    return ToolCall(id="c1", name="fixture_log_search", arguments=arguments or {"query": "x"})


# --- ordering ------------------------------------------------------------------


async def test_hooks_run_in_declared_order() -> None:
    order: list[str] = []
    registry = HookRegistry()

    async def first(session: Session) -> None:
        order.append("first")

    async def second(session: Session) -> None:
        order.append("second")

    registry.register(HookPoint.ON_RUN_START, second, name="second", order=20)
    registry.register(HookPoint.ON_RUN_START, first, name="first", order=10)

    await registry.run_run_start(Session(id="run-1"))

    assert order == ["first", "second"]


async def test_equal_order_falls_back_to_registration_sequence() -> None:
    order: list[str] = []
    registry = HookRegistry()

    for name in ("a", "b", "c"):

        async def hook(session: Session, captured: str = name) -> None:
            order.append(captured)

        registry.register(HookPoint.ON_RUN_START, hook, name=name)

    await registry.run_run_start(Session(id="run-1"))

    assert order == ["a", "b", "c"]


# --- failures ------------------------------------------------------------------


async def test_a_raising_hook_is_recorded_and_the_others_still_run() -> None:
    ran: list[str] = []
    registry = HookRegistry()

    async def broken(session: Session) -> None:
        raise RuntimeError("this hook is wrong")

    async def healthy(session: Session) -> None:
        ran.append("healthy")

    registry.register(HookPoint.ON_RUN_START, broken, name="broken", order=1)
    registry.register(HookPoint.ON_RUN_START, healthy, name="healthy", order=2)

    failures = await registry.run_run_start(Session(id="run-1"))

    assert ran == ["healthy"]
    assert [failure.hook for failure in failures] == ["broken"]
    assert failures[0].point == HookPoint.ON_RUN_START.value
    assert "this hook is wrong" in failures[0].error


async def test_a_raising_pre_tool_use_hook_does_not_deny_by_accident() -> None:
    """A hook that crashed made no decision. Reading a crash as a denial would
    make a broken masking rule silently disable every write in the system."""
    registry = HookRegistry()

    async def broken(call: ToolCall, context: ToolContext) -> None:
        raise RuntimeError("boom")

    registry.register(HookPoint.PRE_TOOL_USE, broken, name="broken")

    decision, _, failures = await registry.run_pre_tool_use(_call(), _context())

    assert isinstance(decision, Allow)
    assert failures


# --- pre_tool_use --------------------------------------------------------------


async def test_a_denial_stops_the_chain() -> None:
    reached: list[str] = []
    registry = HookRegistry()

    async def deny(call: ToolCall, context: ToolContext) -> Deny:
        return Deny(reason="this action needs a human")

    async def later(call: ToolCall, context: ToolContext) -> Allow:
        reached.append("later")
        return Allow()

    registry.register(HookPoint.PRE_TOOL_USE, deny, name="deny", order=1)
    registry.register(HookPoint.PRE_TOOL_USE, later, name="later", order=2)

    decision, arguments, _ = await registry.run_pre_tool_use(_call(), _context())

    assert isinstance(decision, Deny)
    assert decision.reason == "this action needs a human"
    assert reached == []
    assert arguments == {"query": "x"}


async def test_a_rewrite_reaches_the_next_hook_and_the_caller() -> None:
    seen: list[object] = []
    registry = HookRegistry()

    async def mask(call: ToolCall, context: ToolContext) -> Rewrite:
        return Rewrite(arguments={"query": "MASKED"}, reason="credential-shaped argument")

    async def observer(call: ToolCall, context: ToolContext) -> Allow:
        seen.append(dict(call.arguments))
        return Allow()

    registry.register(HookPoint.PRE_TOOL_USE, mask, name="mask", order=1)
    registry.register(HookPoint.PRE_TOOL_USE, observer, name="observer", order=2)

    decision, arguments, _ = await registry.run_pre_tool_use(_call(query="secret"), _context())

    assert isinstance(decision, Allow)
    assert arguments == {"query": "MASKED"}
    assert seen == [{"query": "MASKED"}]


async def test_a_hook_returning_nothing_means_allow() -> None:
    """An observe-only hook should not have to import a result type to say
    "I have no opinion"."""
    registry = HookRegistry()

    async def observer(call: ToolCall, context: ToolContext) -> None:
        return None

    registry.register(HookPoint.PRE_TOOL_USE, observer, name="observer")

    decision, _, failures = await registry.run_pre_tool_use(_call(), _context())

    assert isinstance(decision, Allow)
    assert failures == ()


async def test_a_denial_carries_a_classification_the_model_can_read() -> None:
    assert Deny(reason="needs approval").classification is CapabilityErrorClass.APPROVAL_REQUIRED
    assert (
        Deny(reason="blocked", classification=CapabilityErrorClass.PERMISSION_DENIED).classification
        is CapabilityErrorClass.PERMISSION_DENIED
    )


# --- post_tool_use -------------------------------------------------------------


async def test_post_tool_use_may_replace_the_result() -> None:
    registry = HookRegistry()

    async def redact(
        call: ToolCall, result: CapabilityResult, context: ToolContext
    ) -> CapabilityResult:
        return CapabilityResult.ok(result.capability, value="[redacted]")

    registry.register(HookPoint.POST_TOOL_USE, redact, name="redact")

    produced, _ = await registry.run_post_tool_use(
        _call(), CapabilityResult.ok("fixture_log_search", value={"matches": 412}), _context()
    )

    assert produced.value == "[redacted]"


async def test_post_tool_use_returning_nothing_keeps_the_result() -> None:
    registry = HookRegistry()

    async def observer(call: ToolCall, result: CapabilityResult, context: ToolContext) -> None:
        return None

    registry.register(HookPoint.POST_TOOL_USE, observer, name="observer")

    original = CapabilityResult.ok("fixture_log_search", value={"matches": 412})
    produced, failures = await registry.run_post_tool_use(_call(), original, _context())

    assert produced is original
    assert failures == ()


# --- the other observe-only points ---------------------------------------------


async def test_every_lifecycle_point_has_a_dispatcher() -> None:
    """Six points, and a registry that silently dropped one would be very hard
    to notice from the outside."""
    assert {member.value for member in HookPoint} == {
        "on_run_start",
        "pre_tool_use",
        "post_tool_use",
        "on_turn_end",
        "on_run_end",
        "on_cancel",
    }


async def test_turn_end_and_run_end_and_cancel_dispatch() -> None:
    seen: list[str] = []
    registry = HookRegistry()
    session = Session(id="run-1")

    async def at_turn_end(session_: Session, turn: Turn) -> None:
        seen.append("turn")

    async def at_run_end(session_: Session, result: object) -> None:
        seen.append("run")

    async def at_cancel(session_: Session) -> None:
        seen.append("cancel")

    registry.register(HookPoint.ON_TURN_END, at_turn_end, name="t")
    registry.register(HookPoint.ON_RUN_END, at_run_end, name="r")
    registry.register(HookPoint.ON_CANCEL, at_cancel, name="c")

    await registry.run_turn_end(session, Turn(index=1))
    await registry.run_run_end(session, None)
    await registry.run_cancel(session)

    assert seen == ["turn", "run", "cancel"]


def test_an_empty_registry_is_falsy_at_every_point() -> None:
    registry = HookRegistry()

    assert registry.hooks_at(HookPoint.PRE_TOOL_USE) == ()
