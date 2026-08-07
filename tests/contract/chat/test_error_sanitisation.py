"""No chat message carries exception detail, asserted by fault injection.

A secret-looking string is planted inside an exception's own message — the shape
a library's error routinely takes — and the failure is pushed through the chat
sink on every platform. What reaches the transport must name the exception's
type and nothing else; the detail must still be logged, because a surface that
hides the failure from the operator too has traded one problem for another.
"""

from __future__ import annotations

import pytest

from gateway.chat.port import ChatPlatform, ChatTarget
from gateway.chat.sink import ChatSink
from platform.guardrails.engine import GuardrailEngine
from platform.guardrails.sinks import Sink, SinkGuard
from tests.contract.chat.conftest import RecordingTransport, no_wait, payload_texts

pytestmark = pytest.mark.contract

SENTINEL = "sk-live-51H8ZqfakebutsecretlookingAB12"


def _sink(platform: ChatPlatform, target: ChatTarget) -> ChatSink:
    return ChatSink(
        platform=platform,
        target=target,
        guard=SinkGuard(engine=GuardrailEngine()),
        sleep=no_wait,
    )


async def test_an_exception_reaches_chat_as_its_type_name_only(
    platform: ChatPlatform, target: ChatTarget, transport: RecordingTransport
) -> None:
    failure = RuntimeError(f"postgres://ninjasre:{SENTINEL}@db.internal:5432/runs is unreachable")

    await _sink(platform, target).failed(failure)

    delivered = payload_texts(transport.calls)
    assert SENTINEL not in delivered
    assert "db.internal" not in delivered
    assert "RuntimeError" in delivered


async def test_a_secret_in_ordinary_report_text_is_redacted_before_it_is_posted(
    platform: ChatPlatform, target: ChatTarget, transport: RecordingTransport
) -> None:
    """The guardrail engine is on the way out as well as the way in."""
    await _sink(platform, target).say(f"the credential in the pod spec is {SENTINEL}")

    delivered = payload_texts(transport.calls)
    assert SENTINEL not in delivered


async def test_the_full_detail_is_still_available_to_a_local_reader(
    platform: ChatPlatform, target: ChatTarget
) -> None:
    """Redacting at the sink means the operator at the terminal still sees it."""
    guard = SinkGuard(engine=GuardrailEngine())
    failure = RuntimeError(f"connection string {SENTINEL} refused")

    assert SENTINEL in guard.render_failure(failure, sink=Sink.CLI)
    assert SENTINEL not in guard.render_failure(failure, sink=Sink.CHAT)


async def test_a_failure_while_streaming_progress_does_not_leak_either(
    platform: ChatPlatform, target: ChatTarget, transport: RecordingTransport
) -> None:
    sink = _sink(platform, target)
    await sink.progress_started("investigating…")

    await sink.failed(ValueError(f"bad token {SENTINEL}"))

    delivered = payload_texts(transport.calls)
    assert SENTINEL not in delivered
    assert "ValueError" in delivered
