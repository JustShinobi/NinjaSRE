"""Asking a node for something only its command line knows.

Three readings decided this cluster's only total outage and none of them is a
REST endpoint: a node's failed units, whether its bridges exist, and a thin
pool's metadata fill. Reaching them means something holds an SSH identity, and
Article IV forbids that something being the agent — so the agent names a
command and an executor holds the key.

What this tool adds on top of the executor is the part an investigation needs:

**The four outcomes stay four.** Ran and was content; ran and was unhappy; was
refused; could not be reached. An investigation acts differently on each, and a
tool that returned "failed" for all of them would make them one.

**A write is never made by accident.** The tool takes no flag for it. A change
goes through the remediation path that requires an approval, and this tool
reports that rather than quietly doing it.
"""

from __future__ import annotations

import pytest

from capabilities.tools.node import binding
from capabilities.tools.node.run_on_node import TOOL_NAME, run_on_node

pytestmark = pytest.mark.unit


class _Access:
    def __init__(self, result: object = None) -> None:
        self.result = result
        self.asked: list[tuple[str, str]] = []

    async def run(self, *, node: str, command_id: str) -> object:
        self.asked.append((node, command_id))
        return self.result


def _result(**overrides: object) -> object:
    from gateway.executor.service import ExecutionResult

    fields: dict[str, object] = {
        "node": "pve01",
        "command_id": "failed-units",
        "stdout": "nginx.service loaded failed failed",
    }
    fields.update(overrides)
    return ExecutionResult(**fields)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _unbound() -> object:
    previous = binding.bind(None)
    yield
    binding.restore(previous)


async def test_a_deployment_with_no_executor_says_so_rather_than_reporting_nothing() -> None:
    from core.capability.result import CapabilityErrorClass

    result = await run_on_node("pve01", "failed-units")

    assert not result.succeeded
    assert result.error.classification is CapabilityErrorClass.UNAVAILABLE


async def test_a_reading_comes_back_with_the_node_and_command_that_produced_it() -> None:
    access = _Access(result=_result())
    binding.bind(access)

    result = await run_on_node("pve01", "failed-units")

    assert result.succeeded
    assert access.asked == [("pve01", "failed-units")]
    assert "nginx.service" in result.value["stdout"]
    assert result.value["node"] == "pve01"


async def test_a_refused_command_is_an_invalid_argument_not_an_outage() -> None:
    """The deployment is fine; the caller asked for something nobody declared."""
    from core.capability.result import CapabilityErrorClass

    binding.bind(
        _Access(result=_result(refused=True, reason="no command called 'curl' is declared"))
    )

    result = await run_on_node("pve01", "curl")

    assert not result.succeeded
    assert result.error.classification is CapabilityErrorClass.INVALID_ARGUMENTS


async def test_a_node_that_could_not_be_reached_is_unavailable() -> None:
    from core.capability.result import CapabilityErrorClass

    binding.bind(_Access(result=_result(unreachable=True, reason="no route to host")))

    result = await run_on_node("pve01", "failed-units")

    assert result.error.classification is CapabilityErrorClass.UNAVAILABLE


async def test_a_command_the_node_ran_unhappily_is_a_finding_with_its_output() -> None:
    """Exit one from `systemctl list-units` is still the answer to the question;
    losing the output because the code was non-zero loses the finding."""
    binding.bind(_Access(result=_result(exit_code=1, stderr="Failed to list units")))

    result = await run_on_node("pve01", "failed-units")

    assert not result.succeeded
    assert "Failed to list units" in result.error.message


async def test_the_tool_cannot_be_asked_to_make_a_change() -> None:
    """No parameter for it. A change goes through the path that needs approval,
    and a read tool that could write would be that path's way around itself."""
    import inspect

    assert "intends_write" not in inspect.signature(run_on_node).parameters


async def test_the_tool_is_discoverable_under_its_declared_name() -> None:
    from core.capability.registered import capability_marker

    assert TOOL_NAME == "run_on_node"
    assert capability_marker(run_on_node) is not None
