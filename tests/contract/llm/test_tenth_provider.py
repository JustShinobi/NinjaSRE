"""Adding a provider is an adapter and a registry row, and nothing else.

The claim is easy to make and easy to be wrong about — a layer accumulates
provider-specific branches, and nobody notices until the tenth one needs a
change in six files. So this adds a tenth provider here, in the test, and drives
the whole stack with it: normalisation, tool calling, retry, accounting,
structured output, streaming.

Deliberately a *permanent* test rather than an experiment that was run once and
removed. An experiment proves the claim held on the day somebody checked; this
fails the build the day it stops holding.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

import pytest
from capability_schemas import CAPABILITY_SCHEMAS
from cassettes import (
    EXPECTED_STRUCTURED,
    EXPECTED_TEXT,
    EXPECTED_TOOL_ARGUMENTS,
    EXPECTED_TOOL_NAME,
)
from conftest import RecordedTransport, transport_failure

from core.llm.client import ProviderClient
from core.llm.credentials import StaticCredentialResolver
from core.llm.failures import FailureClass
from core.llm.providers import adapter_for, register_adapter, registered_provider_ids
from core.llm.providers.openai_compat import OpenAiCompatibleAdapter
from core.llm.registry import ModelDescriptor, ModelRegistry, Pricing
from core.llm.retry import RetryPolicy
from core.llm.schema import (
    AdditionalPropertiesRule,
    SchemaDialect,
    SchemaNormaliser,
    dialect_for,
    dialect_violations,
    register_dialect,
)
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

TENTH_PROVIDER = "acme_inference"


class AcmeAdapter(OpenAiCompatibleAdapter):
    """A tenth provider, speaking a wire NinjaSRE already knows.

    The realistic case: a new provider is almost always OpenAI-wire compatible
    with its own quirks. Here the quirk is that it rejects ``anyOf`` outright,
    which is a dialect row and not code.
    """

    provider_identifier = TENTH_PROVIDER


ACME_DIALECT = SchemaDialect(
    provider_id=TENTH_PROVIDER,
    allows_union_types=False,
    allows_any_of=False,
    allows_nested_composition=False,
    allows_refs=False,
    additional_properties=AdditionalPropertiesRule.FORCE_FALSE,
    allows_validation_keywords=False,
    supported_formats=frozenset({"date-time"}),
    max_tool_name_length=40,
    max_tool_description_length=512,
    max_schema_depth=5,
)


@pytest.fixture(name="acme_registry")
def _acme_registry() -> ModelRegistry:
    """Return a registry carrying the tenth provider's single row."""
    registry = ModelRegistry()
    registry.register(
        ModelDescriptor(
            model_id="acme-1",
            provider_id=TENTH_PROVIDER,
            context_window=256_000,
            max_output_tokens=16_384,
            supports_structured_output=False,
            supports_parallel_tool_calls=False,
            pricing=Pricing(input_per_million=0.5, output_per_million=1.5),
            pricing_as_of=date(2026, 8, 4),
            inferred=False,
        )
    )
    return registry


@pytest.fixture(name="acme_registered", autouse=True)
def _acme_registered() -> Any:
    """Register the tenth provider's adapter and dialect for the module's tests."""
    register_adapter(AcmeAdapter())
    register_dialect(ACME_DIALECT)
    yield
    # Left registered: a provider registered at runtime staying registered is
    # the behaviour, and the tests below are the only ones that name it.


def _client(acme_registry: ModelRegistry, transport: RecordedTransport) -> ProviderClient:
    async def _no_sleep(_seconds: float) -> None:
        return None

    return ProviderClient(
        adapter=adapter_for(TENTH_PROVIDER),
        descriptor=acme_registry.default_for_provider(TENTH_PROVIDER),
        transport=transport,
        credentials=StaticCredentialResolver(
            {TENTH_PROVIDER: {"api_key": "test-key", "base_url": "https://example.invalid/v1"}}
        ),
        retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=0.0),
        jitter=lambda: 0.0,
        sleeper=_no_sleep,
    )


def _text_document() -> Mapping[str, Any]:
    return {
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": EXPECTED_TEXT},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1_000, "completion_tokens": 200},
    }


def _tool_call_document(name: str, arguments: str) -> Mapping[str, Any]:
    return {
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": name, "arguments": arguments},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 1_000, "completion_tokens": 200},
    }


def test_registering_the_adapter_is_all_the_lookup_needs() -> None:
    assert TENTH_PROVIDER in registered_provider_ids()
    assert adapter_for(TENTH_PROVIDER).provider_id == TENTH_PROVIDER


def test_the_new_dialect_normalises_the_whole_catalogue() -> None:
    dialect = dialect_for(TENTH_PROVIDER)
    assert dialect is ACME_DIALECT

    for tool in SchemaNormaliser(dialect).normalise_all(CAPABILITY_SCHEMAS):
        assert not dialect_violations(tool, dialect), tool.name


async def test_a_turn_works_end_to_end(acme_registry: ModelRegistry) -> None:
    transport = RecordedTransport(responses=[_text_document()])
    result = await _client(acme_registry, transport).invoke(
        InvokeRequest(messages=(Message(role=Role.USER, text="hello"),))
    )

    assert result.succeeded, result.failure_message
    assert result.text == EXPECTED_TEXT
    assert result.provider_id == TENTH_PROVIDER


async def test_tool_calling_works_without_touching_the_client(
    acme_registry: ModelRegistry,
) -> None:
    transport = RecordedTransport(
        responses=[_tool_call_document(EXPECTED_TOOL_NAME, '{"namespace": "checkout"}')]
    )
    request = InvokeRequest(
        messages=(Message(role=Role.USER, text="list pods"),),
        tools=(
            ToolSchema(
                name=EXPECTED_TOOL_NAME,
                description="List pods.",
                parameters={"type": "object", "properties": {"namespace": {"type": "string"}}},
            ),
        ),
    )

    result = await _client(acme_registry, transport).invoke(request)

    assert result.finish_reason is FinishReason.TOOL_CALLS
    assert dict(result.tool_calls[0].arguments) == EXPECTED_TOOL_ARGUMENTS


async def test_retry_and_classification_are_inherited(acme_registry: ModelRegistry) -> None:
    transport = RecordedTransport(
        responses=[transport_failure(status_code=429, message="slow down"), _text_document()]
    )

    result = await _client(acme_registry, transport).invoke(
        InvokeRequest(messages=(Message(role=Role.USER, text="hello"),))
    )

    assert result.succeeded
    assert result.attempts[0].classification is FailureClass.RATE_LIMITED


async def test_cost_accounting_is_inherited(acme_registry: ModelRegistry) -> None:
    transport = RecordedTransport(responses=[_text_document()])

    result = await _client(acme_registry, transport).invoke(
        InvokeRequest(messages=(Message(role=Role.USER, text="hello"),))
    )

    assert result.usage is not None
    # 1000 input at $0.50/M plus 200 output at $1.50/M.
    assert result.usage.cost_usd == pytest.approx(0.0005 + 0.0003)


async def test_structured_output_falls_back_and_records_it(
    acme_registry: ModelRegistry,
) -> None:
    """The provider has no native JSON mode, and the ladder handles it."""
    import json

    from core.llm.structured.tool_coercion import STRUCTURED_OUTPUT_TOOL_NAME

    transport = RecordedTransport(
        responses=[
            _tool_call_document(STRUCTURED_OUTPUT_TOOL_NAME, json.dumps(EXPECTED_STRUCTURED))
        ]
    )

    result = await _client(acme_registry, transport).invoke_structured(
        InvokeRequest(messages=(Message(role=Role.USER, text="diagnose"),)),
        schema={"type": "object", "properties": {"root_cause": {"type": "string"}}},
    )

    assert result.structured == EXPECTED_STRUCTURED
    assert result.structured_mechanism is StructuredMechanism.TOOL_COERCION


async def test_streaming_is_inherited(acme_registry: ModelRegistry) -> None:
    transport = RecordedTransport(
        responses=[],
        chunks=[
            {"choices": [{"index": 0, "delta": {"content": "part one "}}]},
            {"choices": [{"index": 0, "delta": {"content": "part two"}}]},
            {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        ],
    )

    events = [
        event
        async for event in _client(acme_registry, transport).stream(
            InvokeRequest(messages=(Message(role=Role.USER, text="hello"),))
        )
    ]

    text = "".join(event.text for event in events if event.kind is StreamEventKind.TEXT_DELTA)
    assert text == "part one part two"
    assert any(event.kind is StreamEventKind.FINISH for event in events)


async def test_declared_degradations_are_inherited(acme_registry: ModelRegistry) -> None:
    """The row says no parallel tool calls; the result says so too, unprompted."""
    transport = RecordedTransport(responses=[_text_document()])

    result = await _client(acme_registry, transport).invoke(
        InvokeRequest(messages=(Message(role=Role.USER, text="hello"),), parallel_tool_calls=True)
    )

    assert any(
        degradation.kind is DegradationKind.PARALLEL_TOOL_CALLS_SERIALISED
        for degradation in result.degradations
    )
