"""The Slack Web API calls this bot makes, and nothing about authentication.

Six methods. Each builds a ``PlatformCall`` — a path and a JSON payload — and
hands it to the transport, which routes it through the credential proxy. There
is no token here and no parameter that could hold one; the bot token is injected
at the network edge like every other credential in NinjaSRE.

The reply shapes are Slack's own: a posted message answers with ``ts``, which is
both the message identifier and the thread identifier for anything replying to
it. That double duty is why ``thread_ts`` and ``ts`` are the same string for a
thread's first message, and why nothing above this module parses either.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from gateway.chat.port import ChatTransport, PlatformCall, PlatformReply

#: Slack's API root. The path an adapter supplies is a method name on it.
SLACK_API_BASE: Final = "https://slack.com/api/"

#: The integration name the credential proxy resolves the bot token under.
SLACK_INTEGRATION: Final = "slack"


@dataclass(frozen=True, slots=True)
class SlackApi:
    """The Slack Web API, as the six calls this surface actually makes."""

    transport: ChatTransport

    async def post_message(
        self,
        *,
        channel: str,
        text: str,
        thread_ts: str = "",
        blocks: Sequence[Mapping[str, Any]] = (),
    ) -> PlatformReply:
        """Post a message, in a thread when ``thread_ts`` is given."""
        payload: dict[str, Any] = {"channel": channel, "text": text}
        if thread_ts:
            payload["thread_ts"] = thread_ts
        if blocks:
            payload["blocks"] = list(blocks)
        return await self.transport.send(
            PlatformCall(method="POST", path="chat.postMessage", payload=payload)
        )

    async def update_message(
        self,
        *,
        channel: str,
        ts: str,
        text: str,
        blocks: Sequence[Mapping[str, Any]] = (),
    ) -> PlatformReply:
        """Rewrite an existing message in place."""
        payload: dict[str, Any] = {"channel": channel, "ts": ts, "text": text}
        # An empty list, not an absent key: Slack keeps the old blocks when the
        # field is missing, so a closed approval would keep its buttons.
        payload["blocks"] = list(blocks)
        return await self.transport.send(
            PlatformCall(method="POST", path="chat.update", payload=payload)
        )

    async def upload_text_file(
        self,
        *,
        channel: str,
        thread_ts: str,
        filename: str,
        content: str,
        title: str = "",
    ) -> PlatformReply:
        """Deliver a long report as a file rather than as a wall of messages."""
        payload: dict[str, Any] = {
            "channels": channel,
            "filename": filename,
            "content": content,
            "title": title or filename,
        }
        if thread_ts:
            payload["thread_ts"] = thread_ts
        return await self.transport.send(
            PlatformCall(method="POST", path="files.upload", payload=payload)
        )

    async def replies(self, *, channel: str, thread_ts: str, limit: int) -> PlatformReply:
        """Return a thread's earlier messages, oldest first."""
        return await self.transport.send(
            PlatformCall(
                method="GET",
                path="conversations.replies",
                query={"channel": channel, "ts": thread_ts, "limit": str(limit)},
            )
        )

    async def auth_test(self) -> PlatformReply:
        """Return who this bot is, which is how its own user id is discovered."""
        return await self.transport.send(PlatformCall(method="POST", path="auth.test"))

    async def open_socket_connection(self) -> PlatformReply:
        """Return the single-use WebSocket URL Socket Mode connects to."""
        return await self.transport.send(PlatformCall(method="POST", path="apps.connections.open"))


def message_id_of(reply: PlatformReply) -> str:
    """Return the ``ts`` a Slack reply carries, which identifies the message."""
    return str(reply.document.get("ts", ""))


__all__ = [
    "SLACK_API_BASE",
    "SLACK_INTEGRATION",
    "SlackApi",
    "message_id_of",
]
