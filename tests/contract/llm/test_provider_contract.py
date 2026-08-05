"""One suite, nine providers, the same assertions (ADR 0008).

Parity is not a claim, it is this file passing for every provider. Where a
provider genuinely lacks something, the abstraction degrades *explicitly* — the
result carries the degradation — and the assertion is that the degradation is
recorded, never that the behaviour quietly differs.

Everything here runs on recorded documents. No credential, no network, no
tokens, on every pull request.
"""

from __future__ import annotations

import pytest
from capability_schemas import CAPABILITY_SCHEMAS
from cassettes import (
    EXPECTED_CACHED_TOKENS,
    EXPECTED_INPUT_TOKENS,
    EXPECTED_OUTPUT_TOKENS,
    EXPECTED_STRUCTURED,
    EXPECTED_TEXT,
    EXPECTED_TOOL_ARGUMENTS,
    EXPECTED_TOOL_NAME,
    coerced_structured_response,
    prose_structured_response,
    structured_response,
    text_response,
    tool_call_response,
)
from conftest import RecordedTransport, build_client, transport_failure

from core.llm.client import ProviderClient
from core.llm.failures import FailureClass
from core.llm.registry import ModelDescriptor
from core.llm.schema import SchemaNormaliser, dialect_for, dialect_violations
from core.llm.structured.tool_coercion import STRUCTURED_OUTPUT_TOOL_NAME
from core.llm.types import (
    DegradationKind,
    FinishReason,
    InvokeRequest,
    Message,
    Role,
    StreamEventKind,
    StructuredMechanism,
    ToolSchema,
)

pytestmark = pytest.mark.contract


def _tool_request() -> InvokeRequest:
    return InvokeRequest(
        messages=(Message(role=Role.USER, text="List the pods in checkout."),),
        system="You are an SRE investigating a production incident.",
        tools=(
            ToolSchema(
                name=EXPECTED_TOOL_NAME,
                description="List pods, optionally scoped to a namespace.",
                parameters={
                    "type": "object",
                    "properties": {"namespace": {"type": "string"}},
                    "required": ["namespace"],
                },
            ),
        ),
    )


# --- Text, tool calling, and streaming ----------------------------------------


async def test_a_plain_turn_returns_the_model_text(
    client: ProviderClient, simple_request: InvokeRequest
) -> None:
    result = await client.invoke(simple_request)

    assert result.succeeded, result.failure_message
    assert result.text == EXPECTED_TEXT
    assert result.finish_reason is FinishReason.STOP


async def test_tool_calling_round_trips(provider_id: str) -> None:
    transport = RecordedTransport(responses=[tool_call_response(provider_id)])
    client = build_client(provider_id, transport=transport)

    result = await client.invoke(_tool_request())

    assert result.succeeded, result.failure_message
    assert result.finish_reason is FinishReason.TOOL_CALLS
    assert [call.name for call in result.tool_calls] == [EXPECTED_TOOL_NAME]
    assert dict(result.tool_calls[0].arguments) == EXPECTED_TOOL_ARGUMENTS
    assert result.tool_calls[0].id, "every provider must yield an identifier to pair a result back"


async def test_the_tool_definitions_that_go_out_satisfy_the_provider(provider_id: str) -> None:
    """The payload an adapter builds carries schemas the provider accepts.

    This is the half of the contract a response cassette cannot cover: what was
    *sent*. It is also where the combinatorial schema failure lives, which is
    why the whole catalogue goes out at once.
    """
    transport = RecordedTransport(responses=[text_response(provider_id)])
    client = build_client(provider_id, transport=transport)
    request = InvokeRequest(
        messages=(Message(role=Role.USER, text="Investigate."),),
        tools=CAPABILITY_SCHEMAS,
    )

    await client.invoke(request)

    dialect = dialect_for(provider_id)
    for tool in SchemaNormaliser(dialect).normalise_all(CAPABILITY_SCHEMAS):
        assert not dialect_violations(tool, dialect), tool.name
    assert transport.sent, "the adapter sent nothing"


async def test_streaming_yields_text_then_a_finish(
    client: ProviderClient, simple_request: InvokeRequest
) -> None:
    events = [event async for event in client.stream(simple_request)]

    text = "".join(event.text for event in events if event.kind is StreamEventKind.TEXT_DELTA)
    assert text == "The checkout service is failing."
    assert any(event.kind is StreamEventKind.FINISH for event in events)


# --- Accounting ---------------------------------------------------------------


async def test_token_usage_is_recorded_in_neutral_terms(
    client: ProviderClient, simple_request: InvokeRequest
) -> None:
    """Every wire reports usage differently; the record does not.

    Two of the four wires include cached tokens in the prompt count and two do
    not. Getting that wrong makes a cached run look more expensive than an
    uncached one, so the neutral fields are asserted to be disjoint.
    """
    result = await client.invoke(simple_request)

    assert result.usage is not None
    tokens = result.usage.tokens
    assert tokens.output_tokens == EXPECTED_OUTPUT_TOKENS
    assert tokens.cached_input_tokens == EXPECTED_CACHED_TOKENS
    assert tokens.input_tokens == EXPECTED_INPUT_TOKENS - EXPECTED_CACHED_TOKENS
    assert tokens.total_input_tokens == EXPECTED_INPUT_TOKENS


async def test_a_missing_usage_block_is_estimated_and_says_so(provider_id: str) -> None:
    document = text_response(provider_id)
    for key in ("usage", "usageMetadata"):
        document.pop(key, None)

    transport = RecordedTransport(responses=[document])
    result = await build_client(provider_id, transport=transport).invoke(
        InvokeRequest(messages=(Message(role=Role.USER, text="hello"),))
    )

    assert result.usage is not None
    assert result.usage.tokens.estimated is True
    assert any(
        degradation.kind is DegradationKind.USAGE_ESTIMATED for degradation in result.degradations
    )


async def test_an_unpriced_model_costs_none_rather_than_zero(
    provider_id: str, descriptor: ModelDescriptor
) -> None:
    transport = RecordedTransport(responses=[text_response(provider_id)])
    result = await build_client(provider_id, transport=transport).invoke(
        InvokeRequest(messages=(Message(role=Role.USER, text="hello"),))
    )

    assert result.usage is not None
    if descriptor.pricing is None:
        assert result.usage.cost_usd is None
    else:
        assert result.usage.cost_usd is not None
        assert result.usage.cost_usd > 0


# --- Structured output --------------------------------------------------------


async def test_structured_output_works_and_records_its_mechanism(
    provider_id: str, descriptor: ModelDescriptor
) -> None:
    """Whichever route a provider needs, the caller gets the same object."""
    if descriptor.supports_structured_output:
        document = structured_response(provider_id, EXPECTED_STRUCTURED)
        expected_mechanism = StructuredMechanism.NATIVE
    else:
        document = coerced_structured_response(provider_id, EXPECTED_STRUCTURED)
        expected_mechanism = StructuredMechanism.TOOL_COERCION

    transport = RecordedTransport(responses=[document])
    client = build_client(provider_id, transport=transport)

    result = await client.invoke_structured(
        InvokeRequest(messages=(Message(role=Role.USER, text="Diagnose."),)),
        schema={
            "type": "object",
            "properties": {"root_cause": {"type": "string"}, "confidence": {"type": "number"}},
            "required": ["root_cause", "confidence"],
        },
    )

    assert result.succeeded, result.failure_message
    assert result.structured == EXPECTED_STRUCTURED
    assert result.structured_mechanism is expected_mechanism


async def test_prose_parsing_recovers_a_local_model_answer(provider_id: str) -> None:
    """The last resort works, and is loudly labelled as the last resort."""
    registry_descriptor = build_client(
        provider_id, transport=RecordedTransport(responses=[])
    ).descriptor
    from dataclasses import replace

    descriptor = replace(registry_descriptor, supports_structured_output=False)

    transport = RecordedTransport(
        responses=[prose_structured_response(provider_id, EXPECTED_STRUCTURED)]
    )
    client = build_client(provider_id, transport=transport, descriptor=descriptor)

    result = await client.invoke_structured(
        InvokeRequest(messages=(Message(role=Role.USER, text="Diagnose."),)),
        schema={"type": "object", "properties": {"root_cause": {"type": "string"}}},
    )

    assert result.structured == EXPECTED_STRUCTURED
    assert result.structured_mechanism is StructuredMechanism.PROSE_PARSING
    assert any(
        degradation.kind is DegradationKind.STRUCTURED_OUTPUT_FALLBACK
        for degradation in result.degradations
    )


async def test_the_coercion_tool_never_reaches_the_caller(provider_id: str) -> None:
    """Scaffolding must not look like a capability the runtime can execute."""
    from dataclasses import replace

    base = build_client(provider_id, transport=RecordedTransport(responses=[])).descriptor
    descriptor = replace(base, supports_structured_output=False)

    transport = RecordedTransport(
        responses=[coerced_structured_response(provider_id, EXPECTED_STRUCTURED)]
    )
    client = build_client(provider_id, transport=transport, descriptor=descriptor)

    result = await client.invoke_structured(
        InvokeRequest(messages=(Message(role=Role.USER, text="Diagnose."),)),
        schema={"type": "object", "properties": {"root_cause": {"type": "string"}}},
    )

    assert STRUCTURED_OUTPUT_TOOL_NAME not in {call.name for call in result.tool_calls}


# --- Failure handling ---------------------------------------------------------


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (429, FailureClass.RATE_LIMITED),
        (503, FailureClass.TRANSIENT),
        (401, FailureClass.AUTH),
    ],
)
async def test_failures_classify_the_same_way_everywhere(
    provider_id: str, status_code: int, expected: FailureClass
) -> None:
    transport = RecordedTransport(
        responses=[transport_failure(status_code=status_code, message="upstream said no")] * 3
    )
    client = build_client(provider_id, transport=transport)

    result = await client.invoke(InvokeRequest(messages=(Message(role=Role.USER, text="hi"),)))

    assert result.failure is expected
    assert result.partial is True


async def test_a_transient_failure_is_retried_and_then_succeeds(provider_id: str) -> None:
    transport = RecordedTransport(
        responses=[
            transport_failure(status_code=503, message="overloaded"),
            text_response(provider_id),
        ]
    )
    client = build_client(provider_id, transport=transport)

    result = await client.invoke(InvokeRequest(messages=(Message(role=Role.USER, text="hi"),)))

    assert result.succeeded, result.failure_message
    assert len(result.attempts) == 2
    assert result.attempts[0].classification is FailureClass.TRANSIENT
    assert result.attempts[0].delay_seconds > 0


async def test_a_rejected_schema_is_not_retried(provider_id: str) -> None:
    """Repeating a rejected schema spends quota to learn what is already known."""
    transport = RecordedTransport(
        responses=[
            transport_failure(status_code=400, message="Invalid schema for function 'x'"),
        ]
    )
    client = build_client(provider_id, transport=transport)

    result = await client.invoke(InvokeRequest(messages=(Message(role=Role.USER, text="hi"),)))

    assert result.failure is FailureClass.SCHEMA_REJECTED
    assert len(result.attempts) == 1
    assert len(transport.sent) == 1


async def test_a_provider_failure_never_escapes_as_an_exception(provider_id: str) -> None:
    """The caller keeps its prior work and decides."""
    transport = RecordedTransport(
        responses=[transport_failure(status_code=500, message="boom")] * 5
    )
    client = build_client(provider_id, transport=transport, max_attempts=2)

    result = await client.invoke(InvokeRequest(messages=(Message(role=Role.USER, text="hi"),)))

    assert result.partial is True
    assert result.failure is not None
    assert result.finish_reason is FinishReason.ERROR


# --- Guards -------------------------------------------------------------------


async def test_a_request_larger_than_the_context_window_is_refused_before_dispatch(
    provider_id: str, descriptor: ModelDescriptor
) -> None:
    """Cheaper to refuse here than to learn it from the provider."""
    from dataclasses import replace

    tiny = replace(descriptor, context_window=2_048)
    transport = RecordedTransport(responses=[text_response(provider_id)])
    client = build_client(provider_id, transport=transport, descriptor=tiny)

    result = await client.invoke(
        InvokeRequest(messages=(Message(role=Role.USER, text="x" * 200_000),))
    )

    assert result.failure is FailureClass.CONTEXT_EXCEEDED
    assert not transport.sent, "nothing should reach the provider"


async def test_a_tool_call_for_a_tool_that_was_not_sent_is_discarded(provider_id: str) -> None:
    """Executing an unoffered capability is not an option; failing the turn is worse."""
    transport = RecordedTransport(responses=[tool_call_response(provider_id)])
    client = build_client(provider_id, transport=transport)

    request = InvokeRequest(
        messages=(Message(role=Role.USER, text="go"),),
        tools=(
            ToolSchema(
                name="a_different_tool",
                description="Something else.",
                parameters={"type": "object"},
            ),
        ),
    )
    result = await client.invoke(request)

    assert result.tool_calls == ()
    assert any(
        degradation.kind is DegradationKind.UNKNOWN_TOOL_CALL_DISCARDED
        for degradation in result.degradations
    )


async def test_a_provider_without_parallel_calls_records_the_degradation(
    provider_id: str, descriptor: ModelDescriptor
) -> None:
    from dataclasses import replace

    serial = replace(descriptor, supports_parallel_tool_calls=False)
    transport = RecordedTransport(responses=[text_response(provider_id)])
    client = build_client(provider_id, transport=transport, descriptor=serial)

    result = await client.invoke(
        InvokeRequest(messages=(Message(role=Role.USER, text="go"),), parallel_tool_calls=True)
    )

    assert any(
        degradation.kind is DegradationKind.PARALLEL_TOOL_CALLS_SERIALISED
        for degradation in result.degradations
    )


async def test_reasoning_effort_is_ignored_with_a_note_where_unsupported(
    provider_id: str, descriptor: ModelDescriptor
) -> None:
    from dataclasses import replace

    from core.llm.types import ReasoningEffort

    plain = replace(descriptor, supports_reasoning_effort=False)
    transport = RecordedTransport(responses=[text_response(provider_id)])
    client = build_client(provider_id, transport=transport, descriptor=plain)

    result = await client.invoke(
        InvokeRequest(
            messages=(Message(role=Role.USER, text="go"),),
            reasoning_effort=ReasoningEffort.HIGH,
        )
    )

    assert any(
        degradation.kind is DegradationKind.REASONING_EFFORT_IGNORED
        for degradation in result.degradations
    )


# --- Prompt caching -----------------------------------------------------------


async def test_rejected_cache_markers_are_retried_once_without_them(
    provider_id: str, descriptor: ModelDescriptor
) -> None:
    """A performance optimisation must not be able to lose a turn."""
    from dataclasses import replace

    cacheable = replace(descriptor, supports_prompt_cache=True)
    transport = RecordedTransport(
        responses=[
            transport_failure(
                status_code=400,
                message="cache_control: this field is no longer supported",
            ),
            text_response(provider_id),
        ]
    )
    client = build_client(provider_id, transport=transport, descriptor=cacheable)

    result = await client.invoke(
        InvokeRequest(
            messages=(Message(role=Role.USER, text="go"),),
            system="S" * 4_000,
            prompt_cache=True,
        )
    )

    assert result.succeeded, result.failure_message
    assert len(transport.sent) == 2
    assert any(
        degradation.kind is DegradationKind.PROMPT_CACHE_MARKERS_REJECTED
        for degradation in result.degradations
    )


async def test_caching_asked_for_where_unsupported_is_recorded_not_silent(
    provider_id: str, descriptor: ModelDescriptor
) -> None:
    from dataclasses import replace

    uncacheable = replace(descriptor, supports_prompt_cache=False)
    transport = RecordedTransport(responses=[text_response(provider_id)])
    client = build_client(provider_id, transport=transport, descriptor=uncacheable)

    result = await client.invoke(
        InvokeRequest(
            messages=(Message(role=Role.USER, text="go"),),
            system="S" * 4_000,
            prompt_cache=True,
        )
    )

    assert any(
        degradation.kind is DegradationKind.PROMPT_CACHE_UNAVAILABLE
        for degradation in result.degradations
    )
