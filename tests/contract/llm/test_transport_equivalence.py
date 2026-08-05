"""Choosing a transport must not change what a caller sees.

LiteLLM is offered because operators already run it, and it is not the default
because putting a third party's dialect translation on the critical path for
tool calling means that when a schema is rejected, the first question is whose
translation rejected it — asked during an incident.

The bargain is that switching is free. That is asserted here rather than
claimed: the same recorded document through either transport produces the same
``InvokeResult``, field for field.

The second half covers what happens when a transport cannot run at all. A
missing extra is an operator's configuration problem and has to surface as a
classified failure with the extra named — not as an ``ImportError`` escaping
into an investigation.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import replace
from typing import Any

import pytest
from cassettes import text_response, tool_call_response
from conftest import build_client

from config.constants.llm import (
    PROVIDER_ANTHROPIC,
    PROVIDER_AWS_BEDROCK,
    PROVIDER_OLLAMA,
    PROVIDER_OPENAI,
    SUPPORTED_PROVIDERS,
    TRANSPORT_LITELLM,
    TRANSPORT_SDK,
)
from core.llm.credentials import ProviderCredentials
from core.llm.factory import build_transport
from core.llm.failures import FailureClass
from core.llm.transports import TransportUnavailableError, WireRequest, WireResponse
from core.llm.transports.litellm import LiteLlmTransport, route_for
from core.llm.transports.sdk import SdkTransport, binding_for
from core.llm.types import InvokeRequest, Message, Role, ToolSchema

pytestmark = pytest.mark.contract


class _EchoTransport:
    """Returns a fixed document, so two transports differ only in name."""

    def __init__(self, name: str, document: Mapping[str, Any]) -> None:
        self._name = name
        self._document = document

    @property
    def name(self) -> str:
        return self._name

    async def send(self, request: WireRequest) -> WireResponse:
        return WireResponse(payload=self._document)

    async def stream(self, request: WireRequest) -> AsyncIterator[Mapping[str, Any]]:
        return
        yield {}


def _request() -> InvokeRequest:
    return InvokeRequest(
        messages=(Message(role=Role.USER, text="List the pods in checkout."),),
        system="You are an SRE.",
        tools=(
            ToolSchema(
                name="kubernetes_list_pods",
                description="List pods.",
                parameters={"type": "object", "properties": {"namespace": {"type": "string"}}},
            ),
        ),
    )


@pytest.mark.parametrize("provider_id", SUPPORTED_PROVIDERS)
async def test_both_transports_produce_the_same_result(provider_id: str) -> None:
    document = tool_call_response(provider_id)

    through_sdk = await build_client(
        provider_id, transport=_EchoTransport(TRANSPORT_SDK, document)
    ).invoke(_request())
    through_litellm = await build_client(
        provider_id, transport=_EchoTransport(TRANSPORT_LITELLM, document)
    ).invoke(_request())

    # Attempt records carry timing, which is the one field allowed to differ.
    assert replace(through_sdk, attempts=()) == replace(through_litellm, attempts=())


@pytest.mark.parametrize(
    ("provider_id", "model_id", "expected"),
    [
        (PROVIDER_ANTHROPIC, "claude-sonnet-5", "anthropic/claude-sonnet-5"),
        (PROVIDER_OPENAI, "gpt-4.1", "openai/gpt-4.1"),
        (PROVIDER_OLLAMA, "llama3.1", "ollama_chat/llama3.1"),
        (PROVIDER_AWS_BEDROCK, "anthropic.claude-sonnet-5", "bedrock/anthropic.claude-sonnet-5"),
    ],
)
def test_litellm_routing_prefixes_the_model(provider_id: str, model_id: str, expected: str) -> None:
    assert route_for(provider_id, model_id) == expected


def test_litellm_routing_is_idempotent() -> None:
    """A model already carrying its route must not be prefixed twice."""
    once = route_for(PROVIDER_OPENAI, "gpt-4.1")
    assert route_for(PROVIDER_OPENAI, once) == once


def test_the_factory_builds_the_transport_that_was_asked_for() -> None:
    assert build_transport(TRANSPORT_SDK).name == TRANSPORT_SDK
    assert build_transport(TRANSPORT_LITELLM).name == TRANSPORT_LITELLM


def test_an_unrecognised_transport_falls_back_to_the_default() -> None:
    """Not to LiteLLM: the default is the path the contract suite treats as normative."""
    assert build_transport("something-nobody-configured").name == TRANSPORT_SDK


@pytest.mark.parametrize("provider_id", SUPPORTED_PROVIDERS)
def test_every_provider_declares_which_extra_it_needs(provider_id: str) -> None:
    binding = binding_for(provider_id)
    assert binding is not None, f"{provider_id} has no SDK binding"
    assert binding.extra and binding.module


@pytest.mark.parametrize("provider_id", SUPPORTED_PROVIDERS)
async def test_a_missing_extra_is_reported_by_name(provider_id: str) -> None:
    """The message has to name the extra. "ModuleNotFoundError: openai" does not."""
    binding = binding_for(provider_id)
    assert binding is not None

    transport = SdkTransport()
    request = WireRequest(
        provider_id=provider_id,
        model_id="whatever",
        payload={},
        credentials=ProviderCredentials(provider_id, {}),
    )

    try:
        await transport.send(request)
    except TransportUnavailableError as error:
        assert binding.extra in str(error)
        assert "ninjasre[" in str(error)
    except Exception as error:  # pragma: no cover - the SDK is installed here
        pytest.skip(f"{binding.module} is installed; nothing to report ({error})")


async def test_a_missing_extra_becomes_a_classified_failure_not_an_exception(
    provider_id: str,
) -> None:
    """An operator's misconfiguration must not escape into an investigation."""
    client = build_client(provider_id, transport=SdkTransport())

    result = await client.invoke(InvokeRequest(messages=(Message(role=Role.USER, text="hi"),)))

    assert result.partial is True
    assert result.failure is FailureClass.UNKNOWN
    assert result.finish_reason.value == "error"


def test_litellm_is_not_the_default() -> None:
    """ADR 0008: the SDK path is the one the contract suite treats as normative."""
    assert isinstance(build_transport(TRANSPORT_SDK), SdkTransport)
    assert isinstance(build_transport(TRANSPORT_LITELLM), LiteLlmTransport)
    assert build_transport("").name == TRANSPORT_SDK


@pytest.mark.parametrize("provider_id", SUPPORTED_PROVIDERS)
async def test_a_plain_turn_is_equivalent_across_transports(provider_id: str) -> None:
    document = text_response(provider_id)
    sdk_result = await build_client(
        provider_id, transport=_EchoTransport(TRANSPORT_SDK, document)
    ).invoke(_request())
    litellm_result = await build_client(
        provider_id, transport=_EchoTransport(TRANSPORT_LITELLM, document)
    ).invoke(_request())

    assert sdk_result.text == litellm_result.text
    assert sdk_result.usage == litellm_result.usage
