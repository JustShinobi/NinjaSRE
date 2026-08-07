"""No credential at the chat boundary, and one refusal vocabulary.

Two things are asserted here and both are structural rather than behavioural.
The transport has no way to hold a credential — the proxy injects it — and every
platform's way of saying "slow down" or "you are not in this channel" arrives as
the same two exception types, because every shared behaviour branches on them.
"""

from __future__ import annotations

import inspect
import json

import pytest

from gateway.chat.port import ChatRateLimited, ChatUnavailable, PlatformCall
from gateway.chat.transport import CHAT_CAPABILITY, MAX_REQUEST_BYTES, ProxiedChatTransport
from integrations._base.errors import IntegrationError, IntegrationErrorReason
from integrations._base.transport import RequestContext
from platform.credentials.proxy.model import OutboundResponse, ProxyRequest

pytestmark = pytest.mark.unit

CONTEXT = RequestContext(org_id="acme", team_id="payments", capability="gateway.chat")


class _Proxy:
    """A credential proxy that records what it was asked to forward."""

    def __init__(
        self, *, status: int = 200, body: bytes = b"{}", headers: dict[str, str] | None = None
    ) -> None:
        self.requests: list[ProxyRequest] = []
        self.status = status
        self.body = body
        self.headers = headers or {}
        self.raises: BaseException | None = None

    async def forward(self, request: ProxyRequest) -> OutboundResponse:
        self.requests.append(request)
        if self.raises is not None:
            raise self.raises
        return OutboundResponse(status_code=self.status, headers=self.headers, body=self.body)


def _transport(proxy: _Proxy) -> ProxiedChatTransport:
    return ProxiedChatTransport(
        transport=proxy,  # type: ignore[arg-type]
        context=CONTEXT,
        integration="slack",
        base_url="https://slack.example/api/",
    )


# --- No credential can get in ---------------------------------------------------


def test_the_transport_has_no_parameter_that_could_hold_a_credential() -> None:
    """Structural, not aspirational: there is nowhere to put a token."""
    parameters = set(inspect.signature(ProxiedChatTransport).parameters)

    assert parameters == {"transport", "context", "integration", "base_url"}
    forbidden = {"token", "secret", "api_key", "bot_token", "password", "authorization"}
    assert not parameters & forbidden


async def test_a_call_is_forwarded_through_the_proxy_and_names_the_integration() -> None:
    proxy = _Proxy(body=b'{"ok": true, "ts": "1"}')

    await _transport(proxy).send(PlatformCall(method="POST", path="chat.postMessage"))

    forwarded = proxy.requests[0]
    assert forwarded.integration == "slack"
    assert forwarded.org_id == "acme"
    assert forwarded.team_id == "payments"
    assert forwarded.capability == CHAT_CAPABILITY
    assert forwarded.url == "https://slack.example/api/chat.postMessage"


async def test_no_forwarded_request_carries_an_authorization_header() -> None:
    proxy = _Proxy(body=b'{"ok": true}')

    await _transport(proxy).send(
        PlatformCall(method="POST", path="chat.postMessage", payload={"text": "hello"})
    )

    headers = {name.lower() for name in proxy.requests[0].headers}
    assert "authorization" not in headers


async def test_a_payload_is_sent_as_json_and_a_query_becomes_a_query_string() -> None:
    proxy = _Proxy(body=b'{"ok": true}')

    await _transport(proxy).send(
        PlatformCall(
            method="GET",
            path="conversations.replies",
            payload={"limit": 5},
            query={"channel": "C1"},
        )
    )

    forwarded = proxy.requests[0]
    assert forwarded.url.endswith("conversations.replies?channel=C1")
    assert json.loads(forwarded.body or b"{}") == {"limit": 5}


async def test_a_call_with_no_payload_sends_no_body() -> None:
    proxy = _Proxy(body=b'{"ok": true}')

    await _transport(proxy).send(PlatformCall(method="POST", path="auth.test"))

    assert proxy.requests[0].body is None


async def test_an_oversized_body_is_refused_before_it_is_sent() -> None:
    proxy = _Proxy()

    with pytest.raises(ChatUnavailable, match="larger than the platform takes"):
        await _transport(proxy).send(
            PlatformCall(
                method="POST",
                path="chat.postMessage",
                payload={"text": "x" * (MAX_REQUEST_BYTES + 1)},
            )
        )
    assert proxy.requests == []


# --- One refusal vocabulary -----------------------------------------------------


async def test_a_429_becomes_a_rate_limit_carrying_the_platforms_own_wait() -> None:
    proxy = _Proxy(status=429, headers={"Retry-After": "4"}, body=b"{}")

    with pytest.raises(ChatRateLimited) as limited:
        await _transport(proxy).send(PlatformCall(method="POST", path="chat.postMessage"))

    assert limited.value.retry_after_seconds == 4.0


async def test_a_rate_limit_reported_in_the_body_is_read_too() -> None:
    """Two of the four put the wait in the payload rather than in a header."""
    proxy = _Proxy(status=429, body=json.dumps({"parameters": {"retry_after": 7}}).encode())

    with pytest.raises(ChatRateLimited) as limited:
        await _transport(proxy).send(PlatformCall(method="POST", path="sendMessage"))

    assert limited.value.retry_after_seconds == 7.0


async def test_a_server_error_becomes_unavailability() -> None:
    proxy = _Proxy(status=503, body=b"")

    with pytest.raises(ChatUnavailable, match="503"):
        await _transport(proxy).send(PlatformCall(method="POST", path="chat.postMessage"))


async def test_a_two_hundred_that_says_not_in_channel_is_unavailability() -> None:
    """One platform reports every refusal with a 200 and ``ok: false``."""
    proxy = _Proxy(body=json.dumps({"ok": False, "error": "not_in_channel"}).encode())

    with pytest.raises(ChatUnavailable) as gone:
        await _transport(proxy).send(PlatformCall(method="POST", path="chat.postMessage"))

    assert gone.value.reason == "not_in_channel"


async def test_a_two_hundred_that_says_rate_limited_is_a_rate_limit() -> None:
    proxy = _Proxy(body=json.dumps({"ok": False, "error": "ratelimited"}).encode())

    with pytest.raises(ChatRateLimited):
        await _transport(proxy).send(PlatformCall(method="POST", path="chat.postMessage"))


async def test_a_proxy_rate_limit_is_translated_rather_than_leaking_the_integration_type() -> None:
    proxy = _Proxy()
    proxy.raises = IntegrationError(
        "too many requests",
        integration="slack",
        reason=IntegrationErrorReason.RATE_LIMITED,
    )

    with pytest.raises(ChatRateLimited):
        await _transport(proxy).send(PlatformCall(method="POST", path="chat.postMessage"))


async def test_an_unreachable_proxy_is_unavailability() -> None:
    proxy = _Proxy()
    proxy.raises = IntegrationError(
        "connection refused",
        integration="slack",
        reason=IntegrationErrorReason.PROXY_UNAVAILABLE,
    )

    with pytest.raises(ChatUnavailable):
        await _transport(proxy).send(PlatformCall(method="POST", path="chat.postMessage"))


async def test_a_successful_reply_is_returned_parsed() -> None:
    proxy = _Proxy(body=json.dumps({"ok": True, "ts": "1700.1"}).encode())

    reply = await _transport(proxy).send(PlatformCall(method="POST", path="chat.postMessage"))

    assert reply.ok
    assert reply.document["ts"] == "1700.1"


async def test_a_body_that_is_not_json_does_not_raise_on_the_way_back() -> None:
    """A proxy or a CDN answering with HTML must not become a parse error."""
    proxy = _Proxy(body=b"<html>maintenance</html>")

    reply = await _transport(proxy).send(PlatformCall(method="POST", path="chat.postMessage"))

    assert reply.ok
    assert reply.document == {}
