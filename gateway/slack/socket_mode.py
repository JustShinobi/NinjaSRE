"""Socket Mode or HTTP events, and the one place a deployment chooses.

The two differ in exactly one respect — how a payload arrives — and in nothing
else. Socket Mode opens an outbound WebSocket, so a deployment behind a firewall
needs no inbound route at all; HTTP events need a reachable URL and a signature
check, and are what a deployment already terminating TLS wants. Both hand the
same envelope to the same handler, and that is asserted rather than assumed: a
second parsing path would be a second place for a mention to be missed.

**Socket Mode acknowledges before it handles.** Slack redelivers an envelope
nobody acknowledged within three seconds, and an investigation takes longer than
that, so handling first would run every mention twice.

**HTTP events verify before they parse.** An unverified request is not a
payload, it is bytes somebody sent. Verification uses the shared-secret and HMAC
machinery `gateway/webhooks/verification/` already owns, because a second
signature implementation is a second thing to get subtly wrong.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from gateway.chat.port import ChatUnavailable
from gateway.slack.client import SlackApi
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: What Slack sends to prove a URL is ours, before it will send anything else.
URL_VERIFICATION = "url_verification"

#: The envelope types Socket Mode delivers. Anything else is acknowledged and
#: ignored rather than raised on: Slack adds envelope types, and a gateway that
#: crashed on an unfamiliar one would stop delivering the familiar ones too.
ENVELOPE_TYPES = frozenset({"events_api", "interactive", "slash_commands"})


class SlackIngressMode(StrEnum):
    """How this deployment receives Slack payloads."""

    SOCKET_MODE = "socket_mode"
    HTTP_EVENTS = "http_events"


#: What a handler is: it takes one payload and does whatever the surface does.
Handler = Callable[[Mapping[str, Any]], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class Acknowledgement:
    """What goes back on the wire immediately, before anything is handled."""

    envelope_id: str = ""
    body: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        """Return whether there is nothing to send back."""
        return not self.envelope_id and not self.body


@dataclass(slots=True)
class SlackIngress:
    """One inbound path, whichever transport a deployment configured.

    Holds the mode rather than branching per call site, so "which transport is
    this deployment on" is answered once, at construction, by configuration.
    """

    handler: Handler
    mode: SlackIngressMode = SlackIngressMode.SOCKET_MODE
    api: SlackApi | None = None
    handled: int = field(default=0, init=False)

    @classmethod
    def configured(
        cls, handler: Handler, *, mode: str, api: SlackApi | None = None
    ) -> SlackIngress:
        """Return the ingress ``mode`` names.

        Raises:
            ValueError: ``mode`` is not one of the two.
        """
        try:
            chosen = SlackIngressMode(mode)
        except ValueError as unknown:
            raise ValueError(
                f"{mode!r} is not a Slack ingress mode. Choose "
                f"{SlackIngressMode.SOCKET_MODE.value} or {SlackIngressMode.HTTP_EVENTS.value}."
            ) from unknown
        return cls(handler=handler, mode=chosen, api=api)

    async def connection_url(self) -> str:
        """Return the WebSocket URL Socket Mode connects on.

        Raises:
            ChatUnavailable: this deployment is on HTTP events, or Slack refused.
        """
        if self.mode is not SlackIngressMode.SOCKET_MODE:
            raise ChatUnavailable("slack", "this deployment receives events over HTTP")
        if self.api is None:
            raise ChatUnavailable("slack", "socket mode needs an API client to open a connection")
        reply = await self.api.open_socket_connection()
        url = str(reply.document.get("url") or "")
        if not url:
            raise ChatUnavailable("slack", "slack did not return a socket url")
        return url

    async def receive_envelope(self, envelope: Mapping[str, Any]) -> Acknowledgement:
        """Acknowledge ``envelope``, then handle what it carries.

        The acknowledgement is built before the handler runs and returned after,
        which is the shape a caller writing it to the socket needs. What matters
        is that the handler cannot make the acknowledgement late.
        """
        envelope_id = str(envelope.get("envelope_id") or "")
        kind = str(envelope.get("type") or "")
        acknowledgement = Acknowledgement(envelope_id=envelope_id)

        if kind and kind not in ENVELOPE_TYPES:
            logger.info("slack.envelope_ignored", envelope_type=kind)
            return acknowledgement

        payload = envelope.get("payload")
        if isinstance(payload, Mapping):
            await self._handle(payload)
        return acknowledgement

    async def receive_http(self, payload: Mapping[str, Any]) -> Acknowledgement:
        """Handle one verified Events API request, and return what to answer with.

        The caller has already verified the signature. This method takes a
        payload, not a request, precisely so that it cannot be called with one
        that has not been.
        """
        if str(payload.get("type") or "") == URL_VERIFICATION:
            return Acknowledgement(body={"challenge": str(payload.get("challenge") or "")})
        await self._handle(payload)
        return Acknowledgement(body={"ok": True})

    async def _handle(self, payload: Mapping[str, Any]) -> None:
        """Run the handler, never letting one payload's failure end the ingress."""
        try:
            await self.handler(payload)
        except Exception as failure:  # noqa: BLE001 — one payload must not stop the socket
            logger.error("slack.handler_failed", error=type(failure).__name__)
        else:
            self.handled += 1


__all__ = [
    "ENVELOPE_TYPES",
    "URL_VERIFICATION",
    "Acknowledgement",
    "Handler",
    "SlackIngress",
    "SlackIngressMode",
]
