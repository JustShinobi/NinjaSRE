"""Discord as a ``ChatPlatform``: guild channels, threads, and components.

A thread is a channel here, so ``post`` addresses ``thread_id`` when there is one
and the parent channel otherwise. Opening the thread is a separate call
(``open_thread``) rather than something ``post`` does implicitly: creating a
thread is a visible act in a guild, and doing it as a side effect of a message
would make a stray mention litter the channel list.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from config.constants.surfaces import CHAT_PLATFORM_DISCORD
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
from gateway.discord import components, events
from gateway.discord.client import DiscordApi, message_id_of


@dataclass(slots=True)
class DiscordPlatform:
    """One Discord application, seen through the shared chat port."""

    transport: ChatTransport
    application_id: str = ""
    api: DiscordApi = field(init=False)

    def __post_init__(self) -> None:
        self.api = DiscordApi(transport=self.transport, application_id=self.application_id)

    @property
    def name(self) -> str:
        """Return which of the four platforms this is."""
        return CHAT_PLATFORM_DISCORD

    @property
    def limits(self) -> PlatformLimits:
        """Return Discord's message and edit-rate bounds."""
        return PlatformLimits.of(CHAT_PLATFORM_DISCORD)

    # -- receive ---------------------------------------------------------------

    def parse_message(self, payload: Mapping[str, Any]) -> InboundMessage | None:
        """Return what ``payload`` says, or ``None`` if it says nothing to this bot."""
        return events.parse_message(payload, application_id=self.application_id)

    def parse_decision(self, payload: Mapping[str, Any]) -> InteractionDecision | None:
        """Return the interaction decision ``payload`` carries, or ``None``."""
        return events.parse_decision(payload)

    def user_of(self, payload: Mapping[str, Any]) -> PlatformUser | None:
        """Return the Discord user ``payload`` was produced by, or ``None``."""
        return events.user_of(payload)

    async def thread_history(self, target: ChatTarget, *, limit: int) -> Sequence[ThreadMessage]:
        """Return up to ``limit`` earlier messages of ``target``, oldest first."""
        reply = await self.api.channel_messages(channel_id=_channel(target), limit=limit)
        raw = reply.document.get("messages")
        if not isinstance(raw, list):
            raw = reply.document.get("result") if isinstance(reply.document, Mapping) else None
        if not isinstance(raw, list):
            return ()
        # Discord answers newest first; a transcript reads oldest first.
        return tuple(
            reversed(
                [
                    ThreadMessage(
                        author=_author(message),
                        text=str(message.get("content") or ""),
                        posted_at=str(message.get("timestamp") or ""),
                        is_bot=_is_bot(message, self.application_id),
                    )
                    for message in raw
                    if isinstance(message, Mapping)
                ]
            )
        )

    # -- stream ----------------------------------------------------------------

    async def post(self, target: ChatTarget, text: str) -> PostedMessage:
        """Post ``text`` to ``target``'s thread, or to its channel if unbound."""
        reply = await self.api.create_message(channel_id=_channel(target), content=text)
        return PostedMessage(target=target, message_id=message_id_of(reply), text=text)

    async def edit(self, message: PostedMessage, text: str) -> PostedMessage:
        """Rewrite ``message`` to say ``text`` and return it as it now reads."""
        await self.api.edit_message(
            channel_id=_channel(message.target), message_id=message.message_id, content=text
        )
        return message.with_text(text)

    async def attach(self, target: ChatTarget, attachment: Attachment) -> PostedMessage:
        """Deliver ``attachment`` to ``target`` as a file."""
        reply = await self.api.create_attachment(
            channel_id=_channel(target),
            filename=attachment.filename,
            content=attachment.content,
            title=attachment.title,
        )
        posted = message_id_of(reply)
        if not posted:
            raise ChatUnavailable(CHAT_PLATFORM_DISCORD, "the file was not accepted")
        return PostedMessage(target=target, message_id=posted, text=attachment.title)

    async def open_thread(self, target: ChatTarget, message_id: str, name: str) -> ChatTarget:
        """Open a thread from ``message_id`` and return ``target`` bound to it.

        Raises:
            ChatUnavailable: Discord refused to create the thread.
        """
        reply = await self.api.start_thread(
            channel_id=target.channel_id, message_id=message_id, name=name
        )
        thread_id = message_id_of(reply)
        if not thread_id:
            raise ChatUnavailable(CHAT_PLATFORM_DISCORD, "the thread was not created")
        return target.in_thread(thread_id)

    # -- render an interaction -------------------------------------------------

    def render_interaction(self, interaction: Interaction) -> InteractiveElement:
        """Return the message and components ``interaction`` is decided with."""
        return components.render(interaction)

    async def send_interaction(
        self, target: ChatTarget, element: InteractiveElement
    ) -> PostedMessage:
        """Show ``element`` in ``target`` and return the message carrying it."""
        rows = element.payload.get("components")
        reply = await self.api.create_message(
            channel_id=_channel(target),
            content=element.fallback_text,
            components=rows if isinstance(rows, list) else (),
        )
        return PostedMessage(
            target=target, message_id=message_id_of(reply), text=element.fallback_text
        )

    async def close_interaction(self, message: PostedMessage, event: InteractionEvent) -> None:
        """Remove ``message``'s components and say what was decided."""
        await self.api.edit_message(
            channel_id=_channel(message.target),
            message_id=message.message_id,
            content=components.outcome_text(event),
        )


def _channel(target: ChatTarget) -> str:
    """Return the channel a post actually goes to: the thread, or the parent."""
    return target.thread_id or target.channel_id


def _author(message: Mapping[str, Any]) -> str:
    """Return the display name of whoever sent ``message``."""
    author = message.get("author")
    if not isinstance(author, Mapping):
        return "unknown"
    return str(author.get("global_name") or author.get("username") or author.get("id") or "unknown")


def _is_bot(message: Mapping[str, Any], application_id: str) -> bool:
    """Return whether ``message`` was sent by a bot, this one included."""
    author = message.get("author")
    if not isinstance(author, Mapping):
        return False
    return bool(author.get("bot")) or str(author.get("id") or "") == application_id


__all__ = ["DiscordPlatform"]
