"""A source bound for one investigation is not the source another one reads.

Both capability bindings held their source in a module-level global. A global is
one cell shared by every asyncio task in the process, and this deployment runs
investigations concurrently — three started inside 82 milliseconds on one
morning. So the second run to bind overwrote the first run's source, and the
first run went on reading it for the rest of its life.

For recall that is not staleness, it is disclosure. ``MemoryRetriever`` refuses a
scope with no team on it, in its own constructor, because an unscoped search is
one that can return another team's incidents; a retriever scoped to team A read
by a run investigating team B is that same search with the scope intact and the
wrong team in it.

Written against both bindings at once, parametrised over the two modules, because
they are one mechanism spelled twice and a property proved of only one of them is
a property that drifts.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from types import ModuleType
from typing import Any

import pytest

from capabilities.tools.system.memory_search import binding as memory_binding
from capabilities.tools.system.topology_query import binding as topology_binding

pytestmark = pytest.mark.unit

#: The two capabilities a composition root has to hand a source to before they
#: can answer anything. Anything that grows a third binding belongs here.
BOTH_BINDINGS = pytest.mark.parametrize(
    "binding",
    [memory_binding, topology_binding],
    ids=["memory_search", "topology_query"],
)


class _Source:
    """Stands in for whatever a composition root binds; identity is the assertion."""

    def __init__(self, name: str) -> None:
        self.name = name


@pytest.fixture(autouse=True)
def leave_both_bindings_as_found() -> Iterator[None]:
    """Leave both bindings exactly as they were found, whatever a test did to them."""
    held = [(module, module.current()) for module in (memory_binding, topology_binding)]
    yield
    for module, previous in held:
        module.restore(previous)


@BOTH_BINDINGS
async def test_two_concurrent_tasks_each_read_the_source_they_bound(
    binding: ModuleType,
) -> None:
    """Two investigations in one process, each reading its own team's source.

    The barrier is the point of the test: both tasks have bound before either
    reads, which is exactly the interleaving a module-level global cannot
    survive and the one this deployment produces every time two alerts land
    together.
    """
    both_bound = asyncio.Barrier(2)

    async def one_run(name: str) -> Any:
        binding.bind(_Source(name))
        await both_bound.wait()
        return binding.current()

    first, second = await asyncio.gather(one_run("first"), one_run("second"))

    assert first is not None and second is not None, "a task lost the source it just bound"
    assert first.name == "first", (
        f"the first run read {first.name!r} back after binding its own source. A run "
        f"reading another run's recall path reads another team's incidents."
    )
    assert second.name == "second", "the second run read the first run's source back"


@BOTH_BINDINGS
async def test_a_source_bound_inside_a_task_does_not_leak_to_the_task_that_spawned_it(
    binding: ModuleType,
) -> None:
    """What one investigation binds ends with it, without the caller undoing anything.

    ``create_task`` rather than awaiting the coroutine directly: a coroutine
    awaited inline runs in its caller's context and is *meant* to be able to
    rebind there. The isolation being asserted is the one a task boundary
    draws, which is the boundary an investigation actually has.
    """
    outer = _Source("outer")
    binding.bind(outer)

    async def inner() -> None:
        binding.bind(_Source("inner"))

    await asyncio.create_task(inner())

    assert binding.current() is outer, (
        "a binding set inside a finished task was still set for its parent. The "
        "next investigation this process starts would inherit it."
    )


@BOTH_BINDINGS
async def test_restore_puts_back_what_bind_replaced_within_one_task(
    binding: ModuleType,
) -> None:
    """The scoping pair still works, which is what the runner binds a run with."""
    first = _Source("first")
    second = _Source("second")
    binding.bind(first)

    replaced = binding.bind(second)
    assert replaced is first, "bind returned something other than the value it displaced"

    binding.restore(replaced)

    assert binding.current() is first, "restore did not put back what bind reported"


@BOTH_BINDINGS
async def test_nothing_is_bound_in_a_task_that_bound_nothing(binding: ModuleType) -> None:
    """A run whose deployment composed no source still reads an honest absence.

    The default has to survive the move off a module global: a capability that
    reads ``None`` reports itself unconfigured, and one that reads a stale
    object from an unrelated context does not.
    """
    binding.bind(_Source("outer"))

    async def inner() -> Any:
        binding.clear()
        return binding.current()

    assert await asyncio.create_task(inner()) is None
