"""Every adapter honours a forced tool call — the suite a tenth provider must pass too.

Parameterised over all nine providers (``conftest.py``'s ``provider_id``
fixture), the same way the rest of the contract suite is. A provider added
later inherits this test by construction: nothing here names one.
"""

from __future__ import annotations

from typing import Any

import pytest
from cassettes import tool_call_response
from conftest import RecordedTransport, build_client

from core.llm.types import InvokeRequest, Message, Role, ToolSchema

pytestmark = pytest.mark.contract

_TOOL = ToolSchema(
    name="list_pods",
    description="List pods in a namespace.",
    parameters={"type": "object", "properties": {"namespace": {"type": "string"}}},
)


def _request(*, force: bool) -> InvokeRequest:
    return InvokeRequest(
        messages=(Message(role=Role.USER, text="List the pods."),),
        tools=(_TOOL,),
        force_tool_call=force,
    )


def _wire_shows_forcing(payload: dict[str, Any]) -> bool:
    """Return whether ``payload`` carries some wire's own way of mandating a tool call.

    Deliberately broad rather than exact per wire: this suite's job is "every
    provider does *something* to force the call", and the per-wire exact shape
    (``functionCallingConfig.mode``, ``tool_choice``, ``toolConfig.toolChoice``)
    is what the unit-level capture tests pin precisely, one adapter at a time.
    """
    tool_choice = payload.get("tool_choice")
    if tool_choice in ("required", {"type": "any"}):
        return True
    config = payload.get("config")
    if isinstance(config, dict):
        tool_config = config.get("toolConfig")
        if isinstance(tool_config, dict):
            calling = tool_config.get("functionCallingConfig")
            if isinstance(calling, dict) and calling.get("mode") == "ANY":
                return True
    bedrock_tool_config = payload.get("toolConfig")
    return isinstance(bedrock_tool_config, dict) and bedrock_tool_config.get("toolChoice") == {
        "any": {}
    }


async def test_a_forced_request_shows_the_wires_own_way_of_mandating_the_call(
    provider_id: str,
) -> None:
    transport = RecordedTransport(responses=[tool_call_response(provider_id)])
    client = build_client(provider_id, transport=transport)

    await client.invoke(_request(force=True))

    assert transport.sent, f"{provider_id} adapter never reached the transport"
    assert _wire_shows_forcing(transport.sent[-1].payload), (
        f"{provider_id}'s payload under force_tool_call=True carries no forcing marker: "
        f"{transport.sent[-1].payload}"
    )


async def test_an_unforced_request_matches_todays_payload_exactly(provider_id: str) -> None:
    """The obligation is a property of the request, not of the adapter: an
    ordinary call — the overwhelming majority of every adapter's traffic —
    must be byte-for-byte what it was before this feature."""
    forced_off = RecordedTransport(responses=[tool_call_response(provider_id)])
    client_off = build_client(provider_id, transport=forced_off)
    await client_off.invoke(_request(force=False))

    baseline = RecordedTransport(responses=[tool_call_response(provider_id)])
    client_baseline = build_client(provider_id, transport=baseline)
    await client_baseline.invoke(
        InvokeRequest(messages=(Message(role=Role.USER, text="List the pods."),), tools=(_TOOL,))
    )

    assert forced_off.sent[-1].payload == baseline.sent[-1].payload
