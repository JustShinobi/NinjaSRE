"""How a chat call reaches a platform without the gateway ever holding a token.

A bot token is a credential, so it lives where every other credential does: in
the vault, injected by the proxy at the network edge. An adapter builds a
``PlatformCall`` — a method, a path, and a payload, all of which are safe in a
trace — and this carries it. There is no constructor parameter here that could
accept a secret, which is what makes "no credential reaches the agent"
structural for the chat surface rather than a rule somebody remembers.

The refusal vocabulary is translated once, here, because all four platforms
signal the same three things differently and every shared behaviour branches on
them: 429 with ``Retry-After`` is a rate limit, 5xx and a dead socket are
unavailability, and a Slack-style ``{"ok": false, "error": "not_in_channel"}``
is unavailability wearing a 200.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import urlencode, urljoin

from gateway.chat.port import ChatRateLimited, ChatUnavailable, PlatformCall, PlatformReply
from integrations._base.errors import IntegrationError
from integrations._base.transport import ProxyTransport, RequestContext
from platform.credentials.proxy.model import ProxyRequest
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: What the proxy's audit line records this call as. Chat is a surface rather
#: than an agent-callable tool, and saying so is what stops a chat post from
#: looking like a capability somebody's investigation ran.
CHAT_CAPABILITY: Final = "gateway.chat"

#: Body sizes above this are refused before they are sent. Every platform
#: rejects them anyway; refusing here means the failure names the reason.
MAX_REQUEST_BYTES: Final = 4 * 1024 * 1024

#: Platform-reported error codes that mean "this surface is gone", whatever
#: status they arrive with. A bot removed from a channel is the common one, and
#: it is the case a run continuing without its surface is about.
_GONE_CODES: Final[frozenset[str]] = frozenset(
    {
        "channel_not_found",
        "not_in_channel",
        "is_archived",
        "account_inactive",
        "token_revoked",
        "invalid_auth",
        "chat_not_found",
        "bot_was_kicked",
        "bot_was_blocked",
        "Missing Access",
        "Unknown Channel",
    }
)


@dataclass(frozen=True, slots=True)
class ProxiedChatTransport:
    """One platform's API, reached through the credential proxy and never around it.

    ``integration`` selects the injection rule, so the same class serves all four
    platforms with four different values and no branch. ``base_url`` is the
    platform's API root; the adapter supplies the rest of the path.
    """

    transport: ProxyTransport
    context: RequestContext
    integration: str
    base_url: str

    async def send(self, call: PlatformCall) -> PlatformReply:
        """Return the platform's answer to ``call``.

        Raises:
            ChatRateLimited: the platform refused for rate.
            ChatUnavailable: nothing came back, or what came back says this
                surface is gone.
        """
        body = _encode(call)
        if len(body or b"") > MAX_REQUEST_BYTES:
            raise ChatUnavailable(self.integration, "the request is larger than the platform takes")

        request = ProxyRequest(
            integration=self.integration,
            org_id=self.context.org_id,
            team_id=self.context.team_id,
            capability=CHAT_CAPABILITY,
            method=call.method,
            url=self._url(call),
            headers={"content-type": "application/json", "accept": "application/json"},
            body=body,
        )
        try:
            answer = await self.transport.forward(request)
        except IntegrationError as failure:
            raise _translate(self.integration, failure) from failure

        return _interpret(self.integration, answer.status_code, answer.headers, answer.body)

    def _url(self, call: PlatformCall) -> str:
        """Return the absolute URL ``call`` addresses."""
        root = self.base_url if self.base_url.endswith("/") else f"{self.base_url}/"
        url = urljoin(root, call.path.lstrip("/"))
        return f"{url}?{urlencode(dict(call.query))}" if call.query else url


def _encode(call: PlatformCall) -> bytes | None:
    """Return ``call``'s body, or ``None`` for a call that carries none."""
    if not call.payload:
        return None
    return json.dumps(dict(call.payload)).encode("utf-8")


def _translate(integration: str, failure: IntegrationError) -> Exception:
    """Return the chat failure an integration-layer failure means."""
    reason = getattr(failure, "reason", None)
    name = getattr(reason, "value", str(reason or "")).lower()
    if "rate" in name:
        return ChatRateLimited(integration)
    return ChatUnavailable(integration, name or "the platform could not be reached")


def _interpret(
    integration: str, status: int, headers: Mapping[str, str], body: bytes
) -> PlatformReply:
    """Return what the platform said, or raise what it refused with."""
    document = _document(body)
    if status == 429:
        raise ChatRateLimited(integration, retry_after_seconds=_retry_after(headers, document))
    if status >= 500:
        raise ChatUnavailable(integration, f"the platform answered {status}")
    if status >= 400:
        raise ChatUnavailable(
            integration, _error_code(document) or f"the platform answered {status}"
        )

    # A 200 that says ``ok: false`` is the shape one of the four uses for every
    # refusal, including the ones that mean the bot is no longer in the channel.
    code = _error_code(document)
    if code:
        if code in _GONE_CODES:
            raise ChatUnavailable(integration, code)
        if code in {"rate_limited", "ratelimited"}:
            raise ChatRateLimited(integration, retry_after_seconds=_retry_after(headers, document))
        raise ChatUnavailable(integration, code)

    return PlatformReply(status=status, document=document)


def _document(body: bytes) -> Mapping[str, Any]:
    """Return ``body`` parsed as a JSON object, or an empty mapping."""
    if not body:
        return {}
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _error_code(document: Mapping[str, Any]) -> str:
    """Return the platform's own error name, whichever field it uses."""
    if document.get("ok") is False:
        return str(document.get("error", "") or "refused")
    for field_name in ("error", "message", "code"):
        value = document.get(field_name)
        if isinstance(value, str) and value and document.get("errors") is not None:
            return value
    return ""


def _retry_after(headers: Mapping[str, str], document: Mapping[str, Any]) -> float:
    """Return the platform's own wait, in seconds, or zero if it did not say."""
    lowered = {name.lower(): value for name, value in headers.items()}
    raw = lowered.get("retry-after", "")
    if raw:
        try:
            return float(raw)
        except ValueError:
            return 0.0
    # Two of the four put the wait in the body instead of the header.
    for path in (("parameters", "retry_after"), ("retry_after",)):
        found: Any = document
        for part in path:
            found = found.get(part) if isinstance(found, Mapping) else None
        if isinstance(found, int | float):
            return float(found)
    return 0.0


__all__ = [
    "CHAT_CAPABILITY",
    "MAX_REQUEST_BYTES",
    "ProxiedChatTransport",
]
