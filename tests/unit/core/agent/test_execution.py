"""Dispatch: what runs together, what runs alone, and what one failure costs.

``parallel_safe`` is a claim the capability's author made, and this is the code
that believes it. Getting the boundary wrong is expensive in both directions —
serialising everything wastes an incident's minutes, and parallelising something
whose author said not to is how five concurrent writes reach production.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from config.constants.investigation import MAX_PARALLEL_TOOL_CALLS
from core.agent.execution import dispatch_calls
from core.agent.session import Session
from core.agent.tool_cache import ToolCallCache
from core.agent.turn import GuardrailActionKind
from core.capability.telemetry import InvocationOutcome
from core.llm.types import ToolCall
from tests.unit.core.agent.conftest import (
    ALWAYS_FAILS,
    BLOCKING_READ,
    LOG_SEARCH,
    METRIC_READ,
    SERIAL_PROBE,
    SLOW_READ,
)

pytestmark = pytest.mark.unit

TOOLS = {
    registered.name: registered
    for registered in (
        LOG_SEARCH,
        METRIC_READ,
        SERIAL_PROBE,
        ALWAYS_FAILS,
        SLOW_READ,
        BLOCKING_READ,
    )
}

#: One slow call. Long enough that the difference between serial and concurrent
#: is far outside scheduler noise, short enough that the suite stays fast.
DELAY = 0.05


def _slow(identifier: str, *, name: str = "fixture_slow_read") -> ToolCall:
    return ToolCall(
        id=identifier, name=name, arguments={"target": identifier, "delay_seconds": DELAY}
    )


async def _dispatch(*calls: ToolCall, session: Session | None = None):  # type: ignore[no-untyped-def]
    return await dispatch_calls(
        calls,
        tools=TOOLS,
        session=session or Session(id="run-1"),
        cache=ToolCallCache(),
        iteration=1,
    )


# --- concurrency ---------------------------------------------------------------


async def test_parallel_safe_calls_run_concurrently() -> None:
    """SC-005. Ten concurrent reads finish in well under ten serial ones."""
    calls = tuple(_slow(f"c{index}") for index in range(10))

    started = time.perf_counter()
    batch = await _dispatch(*calls)
    elapsed = time.perf_counter() - started

    assert len(batch.outcomes) == 10
    assert all(outcome.execution.outcome is InvocationOutcome.SUCCESS for outcome in batch.outcomes)
    assert elapsed < 2 * DELAY * (10 / MAX_PARALLEL_TOOL_CALLS + 1), (
        f"ten {DELAY}s reads took {elapsed:.3f}s — that is serial, not concurrent"
    )


async def test_concurrency_is_bounded_by_the_constant() -> None:
    """The bound is the point. Unbounded fan-out against one vendor is how an
    investigation becomes the incident."""
    live = 0
    peak = 0
    lock = asyncio.Lock()
    original = SLOW_READ.call

    async def counted(target: str, delay_seconds: float = DELAY) -> dict[str, object]:
        nonlocal live, peak
        async with lock:
            live += 1
            peak = max(peak, live)
        try:
            return await original(target, delay_seconds)
        finally:
            async with lock:
                live -= 1

    object.__setattr__(SLOW_READ, "call", counted)
    try:
        await _dispatch(*(_slow(f"c{index}") for index in range(MAX_PARALLEL_TOOL_CALLS * 3)))
    finally:
        object.__setattr__(SLOW_READ, "call", original)

    assert peak <= MAX_PARALLEL_TOOL_CALLS


async def test_a_call_its_author_did_not_declare_safe_runs_alone() -> None:
    live = 0
    peak = 0
    original = SERIAL_PROBE.call

    async def counted(target: str) -> dict[str, object]:
        nonlocal live, peak
        live += 1
        peak = max(peak, live)
        await asyncio.sleep(DELAY)
        live -= 1
        return {"target": target, "reachable": True}

    object.__setattr__(SERIAL_PROBE, "call", counted)
    try:
        await _dispatch(
            *(
                ToolCall(
                    id=f"c{index}", name="fixture_serial_probe", arguments={"target": str(index)}
                )
                for index in range(3)
            )
        )
    finally:
        object.__setattr__(SERIAL_PROBE, "call", original)

    assert peak == 1


async def test_a_serial_call_is_a_barrier_between_the_batches_around_it() -> None:
    """Reordering around a call whose author said "not alongside anything" is
    the same mistake as running it alongside something."""
    order: list[str] = []
    slow_original = SLOW_READ.call
    probe_original = SERIAL_PROBE.call

    async def slow(target: str, delay_seconds: float = DELAY) -> dict[str, object]:
        await asyncio.sleep(delay_seconds)
        order.append(target)
        return {"target": target}

    async def probe(target: str) -> dict[str, object]:
        order.append("barrier")
        return {"target": target, "reachable": True}

    object.__setattr__(SLOW_READ, "call", slow)
    object.__setattr__(SERIAL_PROBE, "call", probe)
    try:
        await _dispatch(
            _slow("before"),
            ToolCall(id="c2", name="fixture_serial_probe", arguments={"target": "x"}),
            _slow("after"),
        )
    finally:
        object.__setattr__(SLOW_READ, "call", slow_original)
        object.__setattr__(SERIAL_PROBE, "call", probe_original)

    assert order == ["before", "barrier", "after"]


async def test_a_synchronous_body_does_not_block_the_event_loop() -> None:
    """A vendor SDK's client is synchronous. Calling one on the loop thread
    stops every other call in the batch, and the symptom is a batch that is
    mysteriously serial."""
    calls = tuple(
        ToolCall(
            id=f"c{index}",
            name="fixture_blocking_read",
            arguments={"target": str(index), "delay_seconds": DELAY},
        )
        for index in range(MAX_PARALLEL_TOOL_CALLS)
    )

    started = time.perf_counter()
    batch = await _dispatch(*calls)
    elapsed = time.perf_counter() - started

    assert all(outcome.execution.outcome is InvocationOutcome.SUCCESS for outcome in batch.outcomes)
    assert elapsed < DELAY * MAX_PARALLEL_TOOL_CALLS * 0.75, (
        f"{MAX_PARALLEL_TOOL_CALLS} blocking reads took {elapsed:.3f}s — "
        "the synchronous bodies ran on the event loop thread"
    )


# --- ordering and isolation ----------------------------------------------------


async def test_results_come_back_in_the_order_the_model_asked() -> None:
    batch = await _dispatch(
        _slow("c1"),
        ToolCall(id="c2", name="fixture_log_search", arguments={"query": "x"}),
        ToolCall(id="c3", name="fixture_metric_read", arguments={"series": "y"}),
    )

    assert [outcome.execution.call_id for outcome in batch.outcomes] == ["c1", "c2", "c3"]
    assert [result.call_id for result in batch.tool_results] == ["c1", "c2", "c3"]


async def test_one_failure_in_a_concurrent_batch_costs_one_call() -> None:
    batch = await _dispatch(
        ToolCall(id="c1", name="fixture_log_search", arguments={"query": "x"}),
        ToolCall(id="c2", name="fixture_always_fails", arguments={}),
        ToolCall(id="c3", name="fixture_metric_read", arguments={"series": "y"}),
    )

    outcomes = {outcome.execution.call_id: outcome.execution for outcome in batch.outcomes}
    assert outcomes["c1"].outcome is InvocationOutcome.SUCCESS
    assert outcomes["c2"].outcome is InvocationOutcome.FAILURE
    assert outcomes["c3"].outcome is InvocationOutcome.SUCCESS


async def test_an_unknown_capability_is_refused_without_stopping_the_batch() -> None:
    batch = await _dispatch(
        ToolCall(id="c1", name="fixture_log_search", arguments={"query": "x"}),
        ToolCall(id="c2", name="fixture_invented_by_the_model", arguments={}),
    )

    refused = batch.outcomes[1].execution
    assert refused.denied
    assert "fixture_log_search" in refused.error_message
    assert any(
        action.kind is GuardrailActionKind.UNKNOWN_CAPABILITY for action in batch.guardrail_actions
    )
    assert batch.outcomes[0].execution.outcome is InvocationOutcome.SUCCESS


async def test_evidence_from_a_concurrent_batch_reaches_the_session() -> None:
    session = Session(id="run-1")

    batch = await _dispatch(_slow("c1"), _slow("c2"), session=session)

    assert len(session.evidence) == 2
    assert [outcome.execution.evidence_ids for outcome in batch.outcomes] == [("e1",), ("e2",)]


async def test_an_empty_batch_is_not_an_error() -> None:
    batch = await _dispatch()

    assert batch.outcomes == ()
    assert batch.guardrail_actions == ()
