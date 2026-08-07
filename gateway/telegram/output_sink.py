"""Telegram as a ``ChatPlatform``: streaming, reports, and inline keyboards.

The one thing worth knowing here: Telegram has no thread-history API. A bot can
read messages as they arrive and nothing else, so ``thread_history`` answers
empty rather than pretending. That is a real difference between the platforms
and it is stated rather than papered over — an adapter that returned a plausible
empty result for a call it never made would be lying about what informed an
investigation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from config.constants.surfaces import CHAT_PLATFORM_TELEGRAM
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
from gateway.telegram import events, keyboards
from gateway.telegram.client import TelegramApi, message_id_of
from platform.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class TelegramPlatform:
    """One Telegram bot, seen through the shared chat port."""

    transport: ChatTransport
    bot_username: str = ""
    api: TelegramApi = field(init=False)

    def __post_init__(self) -> None:
        self.api = TelegramApi(transport=self.transport)

    @property
    def name(self) -> str:
        """Return which of the four platforms this is."""
        return CHAT_PLATFORM_TELEGRAM

    @property
    def limits(self) -> PlatformLimits:
        """Return Telegram's message and edit-rate bounds."""
        return PlatformLimits.of(CHAT_PLATFORM_TELEGRAM)

    # -- receive ---------------------------------------------------------------

    def parse_message(self, payload: Mapping[str, Any]) -> InboundMessage | None:
        """Return what ``payload`` says, or ``None`` if it says nothing to this bot."""
        return events.parse_message(payload, bot_username=self.bot_username)

    def parse_decision(self, payload: Mapping[str, Any]) -> InteractionDecision | None:
        """Return the interaction decision ``payload`` carries, or ``None``."""
        return events.parse_decision(payload)

    def user_of(self, payload: Mapping[str, Any]) -> PlatformUser | None:
        """Return the Telegram user ``payload`` was produced by, or ``None``."""
        return events.user_of(payload)

    async def thread_history(self, target: ChatTarget, *, limit: int) -> Sequence[ThreadMessage]:
        """Return nothing: the Bot API has no way to read a chat's backlog.

        A bot sees messages as they arrive and cannot ask for earlier ones. An
        investigation started here is informed by what was said to it and by the
        alert, and saying so — in the trace, every time it is asked — is better
        than inventing a history call that would always come back empty for a
        subtler reason.
        """
        logger.info(
            "telegram.thread_history_unsupported",
            chat_id=target.channel_id,
            requested=limit,
        )
        return ()

    # -- stream ----------------------------------------------------------------

    async def post(self, target: ChatTarget, text: str) -> PostedMessage:
        """Post ``text`` to ``target`` and return the message that now exists."""
        reply = await self.api.send_message(
            chat_id=target.channel_id, text=text, thread_id=target.thread_id
        )
        return PostedMessage(target=target, message_id=message_id_of(reply), text=text)

    async def edit(self, message: PostedMessage, text: str) -> PostedMessage:
        """Rewrite ``message`` to say ``text`` and return it as it now reads."""
        await self.api.edit_message_text(
            chat_id=message.target.channel_id, message_id=message.message_id, text=text
        )
        return message.with_text(text)

    async def attach(self, target: ChatTarget, attachment: Attachment) -> PostedMessage:
        """Deliver ``attachment`` to ``target`` as a document."""
        reply = await self.api.send_document(
            chat_id=target.channel_id,
            thread_id=target.thread_id,
            filename=attachment.filename,
            content=attachment.content,
            caption=attachment.title,
        )
        posted = message_id_of(reply)
        if not posted:
            raise ChatUnavailable(CHAT_PLATFORM_TELEGRAM, "the document was not accepted")
        return PostedMessage(target=target, message_id=posted, text=attachment.title)

    # -- render an interaction -------------------------------------------------

    def render_interaction(self, interaction: Interaction) -> InteractiveElement:
        """Return the message and keyboard ``interaction`` is decided with."""
        return keyboards.render(interaction)

    async def send_interaction(
        self, target: ChatTarget, element: InteractiveElement
    ) -> PostedMessage:
        """Show ``element`` in ``target`` and return the message carrying it."""
        markup = element.payload.get("reply_markup")
        reply = await self.api.send_message(
            chat_id=target.channel_id,
            text=element.fallback_text,
            thread_id=target.thread_id,
            reply_markup=markup if isinstance(markup, Mapping) else None,
        )
        return PostedMessage(
            target=target, message_id=message_id_of(reply), text=element.fallback_text
        )

    async def close_interaction(self, message: PostedMessage, event: InteractionEvent) -> None:
        """Remove ``message``'s keyboard and say what was decided."""
        await self.api.edit_message_text(
            chat_id=message.target.channel_id,
            message_id=message.message_id,
            text=keyboards.outcome_text(event),
            reply_markup=keyboards.EMPTY_KEYBOARD,
        )


__all__ = ["TelegramPlatform"]
