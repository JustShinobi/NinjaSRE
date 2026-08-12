"""Binding the node capability to the executor this deployment runs.

Twenty-nine defects this session were the same shape: a capability built,
tested, documented, and never called. The executor is the newest one, so the
test that matters here is the last: the boot binds it.

Two decisions this composition makes, and both are refusals:

**No executor address means no binding.** The tool then reports that nothing is
configured, which an operator can act on — rather than reporting that a node is
quiet, which nobody can.

**The executor is reached through the credential proxy like every vendor.** It
holds an SSH key, so from the agent's side it is exactly as privileged as a
cloud API and gets exactly the same treatment.
"""

from __future__ import annotations

import pytest

from gateway.http.node_access import ComposedNodeAccess, compose_node_access

pytestmark = pytest.mark.unit


class _State:
    def __init__(self) -> None:
        self.node_executor: object = None


async def test_a_deployment_that_configured_no_executor_binds_nothing() -> None:
    """The ordinary state of a deployment whose operator has not set one up."""
    from capabilities.tools.node import binding

    previous = binding.bind(None)
    try:
        composed = await compose_node_access(_State(), executor_url="")  # type: ignore[arg-type]

        assert composed is None
        assert binding.current() is None
    finally:
        binding.restore(previous)


async def test_a_configured_executor_is_bound_for_the_tool_to_find() -> None:
    from capabilities.tools.node import binding

    previous = binding.bind(None)
    try:
        composed = await compose_node_access(  # type: ignore[arg-type]
            _State(), executor_url="https://executor.lan.example"
        )

        assert composed is not None
        assert binding.current() is composed
    finally:
        binding.restore(previous)


async def test_the_access_asks_the_executor_for_the_command_it_was_given() -> None:
    class _Transport:
        def __init__(self) -> None:
            self.asked: list[dict[str, object]] = []

        async def request(self, payload: dict[str, object]) -> dict[str, object]:
            self.asked.append(payload)
            return {"node": "pve01", "command_id": "failed-units", "stdout": "nothing failed"}

    transport = _Transport()
    access = ComposedNodeAccess(transport=transport)  # type: ignore[arg-type]

    outcome = await access.run(node="pve01", command_id="failed-units")

    assert transport.asked == [{"node": "pve01", "command_id": "failed-units"}]
    assert outcome.stdout == "nothing failed"
    assert not outcome.refused


async def test_an_executor_that_did_not_answer_reads_as_unreachable() -> None:
    """Not as a refusal: one says the command is not allowed, the other says
    nobody could ask. An investigation acts differently on each."""

    class _Broken:
        async def request(self, payload: dict[str, object]) -> dict[str, object]:
            raise OSError("connection refused")

    outcome = await ComposedNodeAccess(transport=_Broken()).run(  # type: ignore[arg-type]
        node="pve01", command_id="failed-units"
    )

    assert outcome.unreachable
    assert not outcome.refused


async def test_the_executors_own_refusal_survives_the_transport() -> None:
    """The allowlist lives in the executor; a refusal it made must not arrive
    here looking like the node was fine."""

    class _Refusing:
        async def request(self, payload: dict[str, object]) -> dict[str, object]:
            return {
                "node": "pve01",
                "command_id": "curl",
                "refused": True,
                "reason": "no command called 'curl' is declared",
            }

    outcome = await ComposedNodeAccess(transport=_Refusing()).run(  # type: ignore[arg-type]
        node="pve01", command_id="curl"
    )

    assert outcome.refused
    assert "declared" in outcome.reason


def test_the_boot_composes_the_node_access() -> None:
    """The joint. Twenty-nine defects this session were a capability nothing
    called, and a test of the composition alone would have passed for each."""
    import inspect

    from gateway.http import lifespan

    assert "compose_node_access" in inspect.getsource(lifespan)


def test_the_state_declares_the_field_this_composition_writes() -> None:
    """Same shape as the integration-access defect: a slotted dataclass refuses
    an undeclared attribute, and a fake with a __dict__ accepts anything."""
    from gateway.http.state import GatewayState

    assert "node_executor" in GatewayState.__dataclass_fields__
