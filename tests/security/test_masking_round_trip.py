"""Masking is only acceptable to use by default if undoing it is exact.

Redaction destroys a report. An on-call engineer cannot act on "``[REDACTED]``
is OOMKilling", and a control that makes the output useless is a control that
gets switched off during the first incident. Reversibility is the whole reason
masking is the default and redaction is not.

So this is the criterion that matters most in practice: a report produced with
masking on and then restored must be **byte-identical**, for identifier content,
to the same report produced with masking off. Not "close enough", not "the pod
name is in there somewhere" — identical, because anything less means the
engineer is reading a report that has quietly lost a character somewhere.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from typing import Any

import pytest

from core.llm.types import (
    FinishReason,
    InvokeRequest,
    InvokeResult,
    Message,
    Role,
    StreamEvent,
    StreamEventKind,
    TokenEstimate,
    ToolCall,
)
from platform.masking.context import MaskingContext
from platform.masking.llm import MaskingLLMClient
from platform.masking.policy import MaskingLevel, MaskingPolicy

pytestmark = [pytest.mark.security]

POD = "checkout-7d9f8b6c5d-x2n4p"
NAMESPACE = "payments-prod"
CLUSTER = "prod-eu-west-1-blue"
NODE_IP = "10.42.17.203"

REPORT = (
    f"# Root cause\n\n"
    f"Pod {POD} in namespace={NAMESPACE} on cluster={CLUSTER} exceeded its memory\n"
    f"limit and was OOMKilled by the kubelet on node {NODE_IP}. The same pod\n"
    f"({POD}) restarted four times in twelve minutes.\n\n"
    f"| field | value |\n"
    f"|---|---|\n"
    f"| pod | `{POD}` |\n"
    f"| namespace | `{NAMESPACE}` |\n"
    f"| node | `{NODE_IP}` |\n"
)


#: Deliberately smaller than a token and coprime with its length.
_CHUNK = 7


class EchoingClient:
    """A model that answers with whatever it was asked, plus a sentence.

    Echoing is the point. Whatever the boundary sent is what comes back, so the
    round trip is exercised on exactly the text masking produced rather than on
    text a fixture happened to contain.
    """

    def __init__(self, *, suffix: str = "") -> None:
        self.received: list[InvokeRequest] = []
        self._suffix = suffix

    @property
    def provider_id(self) -> str:
        """Return the provider this client stands in for."""
        return "anthropic"

    @property
    def model_id(self) -> str:
        """Return the model this client stands in for."""
        return "claude-sonnet-5"

    def _reply(self, request: InvokeRequest) -> str:
        return (
            "\n".join(message.text for message in request.messages if message.text) + self._suffix
        )

    async def invoke(self, request: InvokeRequest) -> InvokeResult:
        """Return the prompt back as the answer."""
        self.received.append(request)
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            text=self._reply(request),
            finish_reason=FinishReason.STOP,
        )

    async def stream(self, request: InvokeRequest) -> AsyncIterator[StreamEvent]:
        """Yield the prompt back in fixed-size chunks.

        Fixed size rather than per line, and a size no token divides evenly, so
        every token is guaranteed to straddle at least one event boundary. A
        line-at-a-time stub would never exercise the case that breaks a naive
        implementation.
        """
        self.received.append(request)
        reply = self._reply(request)
        for start in range(0, len(reply), _CHUNK):
            yield StreamEvent(kind=StreamEventKind.TEXT_DELTA, text=reply[start : start + _CHUNK])
        yield StreamEvent(kind=StreamEventKind.FINISH, finish_reason=FinishReason.STOP)

    async def invoke_structured(
        self, request: InvokeRequest, schema: Mapping[str, Any]
    ) -> InvokeResult:
        """Return the prompt back inside a structured field."""
        self.received.append(request)
        return InvokeResult(
            provider_id=self.provider_id,
            model_id=self.model_id,
            structured={"summary": self._reply(request)},
            finish_reason=FinishReason.STOP,
        )

    def count_tokens(self, request: InvokeRequest) -> TokenEstimate:
        """Return a crude estimate, which is all this suite needs."""
        return TokenEstimate(tokens=len(self._reply(request)) // 4, estimated=True)


def report_request() -> InvokeRequest:
    """Return the request that carries the report through the boundary."""
    return InvokeRequest(messages=(Message(role=Role.USER, text=REPORT),))


def masked_client(level: MaskingLevel) -> tuple[MaskingLLMClient, MaskingContext, EchoingClient]:
    """Return a client at ``level``, its context, and the model behind it."""
    inner = EchoingClient()
    context = MaskingContext(policy=MaskingPolicy(level=level))
    return MaskingLLMClient(inner=inner, context=context), context, inner


async def test_restoration_is_byte_identical_to_never_masking() -> None:
    """The round trip changes nothing an engineer would read."""
    masked, _, _ = masked_client(MaskingLevel.STANDARD)
    unmasked, _, _ = masked_client(MaskingLevel.OFF)

    restored = await masked.invoke(report_request())
    baseline = await unmasked.invoke(report_request())

    assert restored.text == baseline.text


async def test_the_model_saw_no_identifier() -> None:
    """The other half of the same claim: the round trip really did happen."""
    masked, _, inner = masked_client(MaskingLevel.STANDARD)

    await masked.invoke(report_request())

    seen = inner.received[0].messages[0].text
    for identifier in (POD, NAMESPACE, CLUSTER, NODE_IP):
        assert identifier not in seen


async def test_the_model_can_still_correlate_the_same_pod() -> None:
    """The pod named twice in the report is one token, not two."""
    masked, context, inner = masked_client(MaskingLevel.STANDARD)

    await masked.invoke(report_request())

    seen = inner.received[0].messages[0].text
    token = next(name for name, value in context.mapping.entries().items() if value == POD)
    assert seen.count(token) == REPORT.count(POD)


async def test_a_token_the_model_invented_survives_untouched() -> None:
    """Restoration replaces tokens it issued, and nothing that merely looks like one.

    A model that hallucinates ``NSRE_MASK_POD_99`` must not have it silently
    turned into some other run's pod. An unknown token stays as it is, which is
    visibly wrong rather than invisibly wrong.
    """
    inner = EchoingClient(suffix="\nAlso check NSRE_MASK_POD_99.")
    context = MaskingContext(policy=MaskingPolicy(level=MaskingLevel.STANDARD))
    client = MaskingLLMClient(inner=inner, context=context)

    result = await client.invoke(report_request())

    assert "NSRE_MASK_POD_99" in result.text


async def test_streaming_restores_across_event_boundaries() -> None:
    """A token split across two deltas still comes back whole.

    Streaming is where a naive per-chunk replacement quietly fails: half a
    token in one event and half in the next matches nothing, and the engineer
    reads a report with ``NSRE_MASK_`` in it.
    """
    masked, _, _ = masked_client(MaskingLevel.STANDARD)

    streamed = "".join(
        [
            event.text
            async for event in masked.stream(report_request())
            if event.kind is StreamEventKind.TEXT_DELTA
        ]
    )

    assert POD in streamed
    assert "NSRE_MASK_" not in streamed


async def test_structured_output_is_restored_too() -> None:
    """A structured answer is read by a human as often as prose is."""
    masked, _, _ = masked_client(MaskingLevel.STANDARD)

    result = await masked.invoke_structured(report_request(), schema={"type": "object"})

    assert result.structured is not None
    assert POD in str(result.structured["summary"])


async def test_tool_call_arguments_come_back_unmasked() -> None:
    """A tool takes a real pod name; the token would reach the cluster otherwise."""
    context = MaskingContext(policy=MaskingPolicy(level=MaskingLevel.STANDARD))
    # Allocating the token up front is not a shortcut — it is the stability
    # claim again. The same context masks the report during the call, and if
    # allocation were not stable the tool call below would name a different pod.
    context.mask(REPORT)
    token = next(name for name, value in context.mapping.entries().items() if value == POD)

    class ToolCallingClient(EchoingClient):
        async def invoke(self, request: InvokeRequest) -> InvokeResult:
            self.received.append(request)
            return InvokeResult(
                provider_id=self.provider_id,
                model_id=self.model_id,
                tool_calls=(
                    ToolCall(id="t1", name="kubernetes_describe_pod", arguments={"pod": token}),
                ),
                finish_reason=FinishReason.TOOL_CALLS,
            )

    client = MaskingLLMClient(inner=ToolCallingClient(), context=context)

    result = await client.invoke(report_request())

    assert result.tool_calls[0].arguments == {"pod": POD}
