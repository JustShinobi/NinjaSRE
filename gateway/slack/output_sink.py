"""Slack as a ``ChatPlatform``: the adapter, and nothing that decides anything.

Every method here is a translation. Where a message goes becomes a channel and a
``thread_ts``; a report becomes ``chat.postMessage`` or ``files.upload``; an
approval becomes Block Kit. When the streaming discipline changes, or the
chunking rule, or what an approval shows, nothing in this file changes — which
is the property that makes a fifth platform an adapter rather than a rewrite.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from config.constants.surfaces import CHAT_PLATFORM_SLACK
from core.agent.interaction.closure import InteractionEvent
from core.agent.interaction.models import Interaction
from gateway.chat.port import (
    Attachment,
    ChatTarget,
    ChatTransport,
    ChatUnavailable,
    InboundMessage,
    InteractionDecision,
    InteractiveElement,
    PlatformLimits,
    PlatformUser,
    PostedMessage,
    ThreadMessage,
)
from gateway.slack import events, interactions
from gateway.slack.client import SlackApi, message_id_of


@dataclass(slots=True)
class SlackPlatform:
    """One Slack workspace, seen through the shared chat port."""

    transport: ChatTransport
    bot_user_id: str = ""
    api: SlackApi = field(init=False)

    def __post_init__(self) -> None:
        self.api = SlackApi(transport=self.transport)

    @property
    def name(self) -> str:
        """Return which of the four platforms this is."""
        return CHAT_PLATFORM_SLACK

    @property
    def limits(self) -> PlatformLimits:
        """Return Slack's message and edit-rate bounds."""
        return PlatformLimits.of(CHAT_PLATFORM_SLACK)

    # -- receive ---------------------------------------------------------------

    def parse_message(self, payload: Mapping[str, Any]) -> InboundMessage | None:
        """Return what ``payload`` says, or ``None`` if it says nothing to this bot."""
        return events.parse_message(payload, bot_user_id=self.bot_user_id)

    def parse_decision(self, payload: Mapping[str, Any]) -> InteractionDecision | None:
        """Return the interaction decision ``payload`` carries, or ``None``."""
        return events.parse_decision(payload)

    def user_of(self, payload: Mapping[str, Any]) -> PlatformUser | None:
        """Return the Slack user ``payload`` was produced by, or ``None``."""
        return events.user_of(payload)

    async def thread_history(self, target: ChatTarget, *, limit: int) -> Sequence[ThreadMessage]:
        """Return up to ``limit`` earlier messages of ``target``'s thread, oldest first."""
        reply = await self.api.replies(
            channel=target.channel_id, thread_ts=target.thread_id, limit=limit
        )
        raw = reply.document.get("messages")
        if not isinstance(raw, list):
            return ()
        return tuple(
            ThreadMessage(
                author=str(message.get("user") or message.get("username") or "unknown"),
                text=str(message.get("text") or ""),
                posted_at=str(message.get("ts") or ""),
                is_bot=bool(message.get("bot_id"))
                or str(message.get("user") or "") == self.bot_user_id,
            )
            for message in raw
            if isinstance(message, Mapping)
        )

    # -- stream ----------------------------------------------------------------

    async def post(self, target: ChatTarget, text: str) -> PostedMessage:
        """Post ``text`` to ``target`` and return the message that now exists."""
        reply = await self.api.post_message(
            channel=target.channel_id, text=text, thread_ts=target.thread_id
        )
        return PostedMessage(target=target, message_id=message_id_of(reply), text=text)

    async def edit(self, message: PostedMessage, text: str) -> PostedMessage:
        """Rewrite ``message`` to say ``text`` and return it as it now reads."""
        await self.api.update_message(
            channel=message.target.channel_id, ts=message.message_id, text=text
        )
        return message.with_text(text)

    async def attach(self, target: ChatTarget, attachment: Attachment) -> PostedMessage:
        """Deliver ``attachment`` to ``target`` as a file."""
        reply = await self.api.upload_text_file(
            channel=target.channel_id,
            thread_ts=target.thread_id,
            filename=attachment.filename,
            content=attachment.content,
            title=attachment.title,
        )
        posted = _uploaded_id(reply.document)
        if not posted:
            raise ChatUnavailable(CHAT_PLATFORM_SLACK, "the file upload returned no file")
        return PostedMessage(target=target, message_id=posted, text=attachment.title)

    # -- render an interaction -------------------------------------------------

    def render_interaction(self, interaction: Interaction) -> InteractiveElement:
        """Return the Block Kit control ``interaction`` is decided with."""
        return interactions.render(interaction)

    async def send_interaction(
        self, target: ChatTarget, element: InteractiveElement
    ) -> PostedMessage:
        """Show ``element`` in ``target`` and return the message carrying it."""
        blocks = element.payload.get("blocks")
        reply = await self.api.post_message(
            channel=target.channel_id,
            text=element.fallback_text,
            thread_ts=target.thread_id,
            blocks=blocks if isinstance(blocks, list) else (),
        )
        return PostedMessage(
            target=target, message_id=message_id_of(reply), text=element.fallback_text
        )

    async def close_interaction(self, message: PostedMessage, event: InteractionEvent) -> None:
        """Replace ``message``'s buttons with the outcome ``event`` records."""
        blocks, text = interactions.closed_blocks(event)
        await self.api.update_message(
            channel=message.target.channel_id,
            ts=message.message_id,
            text=text,
            blocks=blocks,
        )


def _uploaded_id(document: Mapping[str, Any]) -> str:
    """Return the identifier a successful ``files.upload`` answered with."""
    uploaded = document.get("file")
    if isinstance(uploaded, Mapping):
        return str(uploaded.get("id") or "")
    return str(document.get("ts") or "")


__all__ = ["SlackPlatform"]
