"""What actually leaves the host, read off the wire, for all nine providers.

This suite is written the way the credential suite is written: it does not
simulate the boundary, it stands on it. A real ``ProviderClient`` with a real
adapter builds a real provider payload, and the transport records the document
that would have gone out. Then the document is flattened to strings and searched
for identifiers that are supposed to have been replaced.

Two things make that a measurement rather than a slogan.

**The scan is exhaustive rather than schema-aware.** It walks every string
reachable from the payload, so it also covers the field a provider adds next
year and the one an adapter puts a system prompt in.

**There is a positive control.** ``test_the_identifiers_are_there_without_masking``
asserts the same payload *does* carry the identifiers when the policy is ``off``.
Without it, a wrapper that dropped the messages entirely would pass with the
highest possible marks.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from typing import Any

import pytest

from config.constants.llm import LOCAL_PROVIDERS, PROVIDER_ANTHROPIC, SUPPORTED_PROVIDERS
from core.llm.client import ProviderClient
from core.llm.credentials import StaticCredentialResolver
from core.llm.providers import adapter_for
from core.llm.registry import build_default_registry
from core.llm.retry import RetryPolicy
from core.llm.transports import WireRequest, WireResponse
from core.llm.types import InvokeRequest, Message, Role
from platform.masking.context import MaskingContext
from platform.masking.llm import MaskingLLMClient
from platform.masking.policy import MaskingLevel, MaskingPolicy

pytestmark = [pytest.mark.security]

#: The identifiers this suite hunts for. Each is the shape of a real one and
#: each is distinctive enough that finding it in a payload is finding a leak
#: rather than a coincidence.
POD = "checkout-7d9f8b6c5d-x2n4p"
CLUSTER = "prod-eu-west-1-blue"
NAMESPACE = "payments-prod"
ACCOUNT_ID = "417290583641"
ARN = "arn:aws:iam::417290583641:role/checkout-task"
HOST_IP = "10.42.17.203"

IDENTIFIERS: tuple[str, ...] = (POD, CLUSTER, NAMESPACE, ACCOUNT_ID, ARN, HOST_IP)

PROMPT = (
    f"Pod {POD} in namespace={NAMESPACE} is OOMKilling on cluster={CLUSTER}. "
    f"The node is {HOST_IP} and the task role is {ARN} in account {ACCOUNT_ID}."
)

SYSTEM = f"You are investigating cluster={CLUSTER}. Report findings for namespace={NAMESPACE}."


class RecordingTransport:
    """Stands in for the network, and keeps the document it was handed.

    This is the outside of the boundary. Everything it receives has left the
    operator's control, which is what makes it the right place to assert from.
    """

    def __init__(self) -> None:
        self.sent: list[WireRequest] = []

    @property
    def name(self) -> str:
        """Return this transport's identifier."""
        return "recording"

    async def send(self, request: WireRequest) -> WireResponse:
        """Record ``request`` and return an empty document.

        The response is deliberately uninteresting. Everything this suite
        asserts is about what went *out*, and the round trip back has its own
        suite in ``test_masking_round_trip.py`` where a stub client makes the
        response the subject instead of a side effect.
        """
        self.sent.append(request)
        return WireResponse(payload={})

    async def stream(self, request: WireRequest) -> AsyncIterator[Mapping[str, Any]]:
        """Record ``request`` and yield nothing; this suite asserts on requests."""
        self.sent.append(request)
        return
        yield {}  # pragma: no cover — makes this an async generator


def build_masked_client(
    provider_id: str,
    *,
    transport: RecordingTransport,
    context: MaskingContext,
) -> MaskingLLMClient:
    """Return the real client for ``provider_id``, wrapped at the masking boundary."""
    registry = build_default_registry()

    async def _no_sleep(_seconds: float) -> None:
        return None

    inner = ProviderClient(
        adapter=adapter_for(provider_id),
        descriptor=registry.default_for_provider(provider_id),
        transport=transport,
        credentials=StaticCredentialResolver(
            {
                provider_id: {
                    "api_key": "test-key-not-a-real-credential",
                    "endpoint": "https://example.invalid",
                    "api_version": "2026-01-01",
                    "deployment": "test-deployment",
                    "region": "eu-west-1",
                    "project": "test-project",
                    "location": "europe-west1",
                    "base_url": "https://example.invalid/v1",
                }
            }
        ),
        retry_policy=RetryPolicy(max_attempts=1),
        jitter=lambda: 0.0,
        sleeper=_no_sleep,
    )
    return MaskingLLMClient(inner=inner, context=context)


def strings_in(value: Any) -> Iterator[str]:
    """Yield every string reachable from ``value``, however it is nested."""
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, bytes):
        yield value.decode("utf-8", errors="replace")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield from strings_in(key)
            yield from strings_in(item)
        return
    if isinstance(value, Sequence):
        for item in value:
            yield from strings_in(item)
        return
    yield repr(value)


def leaked(transport: RecordingTransport) -> tuple[str, ...]:
    """Return the identifiers that appear anywhere in what was sent."""
    found: set[str] = set()
    for request in transport.sent:
        for text in strings_in(request.payload):
            for identifier in IDENTIFIERS:
                if identifier in text:
                    found.add(identifier)
        for text in strings_in(dict(request.routing)):
            for identifier in IDENTIFIERS:
                if identifier in text:
                    found.add(identifier)
    return tuple(sorted(found))


def investigation_request() -> InvokeRequest:
    """Return the request an investigation would build for this incident."""
    return InvokeRequest(
        messages=(
            Message(role=Role.USER, text=PROMPT),
            Message(role=Role.ASSISTANT, text=f"I will look at {POD} first."),
        ),
        system=SYSTEM,
    )


@pytest.mark.parametrize("provider_id", SUPPORTED_PROVIDERS)
async def test_no_identifier_reaches_any_provider(provider_id: str) -> None:
    """Nothing on this list leaves the host, for any of the nine providers."""
    transport = RecordingTransport()
    context = MaskingContext(policy=MaskingPolicy(level=MaskingLevel.STANDARD))
    client = build_masked_client(provider_id, transport=transport, context=context)

    await client.invoke(investigation_request())

    assert transport.sent, "the request never reached the transport"
    assert leaked(transport) == ()


@pytest.mark.parametrize("provider_id", SUPPORTED_PROVIDERS)
async def test_the_identifiers_are_there_without_masking(provider_id: str) -> None:
    """The positive control: with the policy off, the payload does carry them.

    Without this, a wrapper that emptied the request would look perfect.
    """
    transport = RecordingTransport()
    context = MaskingContext(policy=MaskingPolicy(level=MaskingLevel.OFF))
    client = build_masked_client(provider_id, transport=transport, context=context)

    await client.invoke(investigation_request())

    assert set(leaked(transport)) == set(IDENTIFIERS)


async def test_the_mapping_itself_never_leaves() -> None:
    """The mapping is the key to everything the tokens hide."""
    transport = RecordingTransport()
    context = MaskingContext(policy=MaskingPolicy(level=MaskingLevel.STANDARD))
    client = build_masked_client(PROVIDER_ANTHROPIC, transport=transport, context=context)

    await client.invoke(investigation_request())

    assert len(context.mapping) > 0
    sent = " ".join(strings_in(transport.sent[0].payload))
    for value in context.mapping.entries().values():
        assert value not in sent


async def test_a_local_provider_is_exempt_when_the_policy_says_so() -> None:
    """Nothing leaves the host, so masking would cost quality for nothing."""
    provider_id = LOCAL_PROVIDERS[0]
    transport = RecordingTransport()
    context = MaskingContext(policy=MaskingPolicy(level=MaskingLevel.LOCAL_MODELS_EXEMPT))
    client = build_masked_client(provider_id, transport=transport, context=context)

    await client.invoke(investigation_request())

    assert set(leaked(transport)) == set(IDENTIFIERS)
    assert len(context.mapping) == 0


async def test_a_cloud_provider_is_not_exempt_under_the_same_policy() -> None:
    """The other half of ``local_models_exempt``: it resolves per call."""
    transport = RecordingTransport()
    context = MaskingContext(policy=MaskingPolicy(level=MaskingLevel.LOCAL_MODELS_EXEMPT))
    client = build_masked_client(PROVIDER_ANTHROPIC, transport=transport, context=context)

    await client.invoke(investigation_request())

    assert leaked(transport) == ()


async def test_the_same_identifier_gets_the_same_token_across_calls() -> None:
    """Correlation is most of what an investigation does."""
    transport = RecordingTransport()
    context = MaskingContext(policy=MaskingPolicy(level=MaskingLevel.STANDARD))
    client = build_masked_client(PROVIDER_ANTHROPIC, transport=transport, context=context)

    await client.invoke(investigation_request())
    await client.invoke(
        InvokeRequest(messages=(Message(role=Role.USER, text=f"and what about {POD}?"),))
    )

    first = " ".join(strings_in(transport.sent[0].payload))
    second = " ".join(strings_in(transport.sent[1].payload))
    token = next(t for t, value in context.mapping.entries().items() if value == POD)
    assert token in first
    assert token in second
