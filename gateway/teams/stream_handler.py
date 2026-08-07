"""Teams as a ``ChatPlatform``: in-place card updates and everything else.

Streaming on Teams is ``updateActivity`` against the activity the progress
message was posted as, which is why a ``PostedMessage``'s id here is an activity
id rather than a conversation id. The conversation reference is rebuilt from the
target on each call: holding one globally is how a multi-tenant install starts
replying into the wrong tenant's service URL.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from config.constants.surfaces import CHAT_PLATFORM_MICROSOFT_TEAMS
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
from gateway.teams import app, cards
from gateway.teams.app import THREAD_SEPARATOR, ConversationReference
from gateway.teams.bot_handlers import TeamsApi, activity_id_of


@dataclass(slots=True)
class TeamsPlatform:
    """One Teams tenant, seen through the shared chat port."""

    transport: ChatTransport
    bot_id: str = ""
    api: TeamsApi = field(init=False)

    def __post_init__(self) -> None:
        self.api = TeamsApi(transport=self.transport)

    @property
    def name(self) -> str:
        """Return which of the four platforms this is."""
        return CHAT_PLATFORM_MICROSOFT_TEAMS

    @property
    def limits(self) -> PlatformLimits:
        """Return Teams' message and edit-rate bounds."""
        return PlatformLimits.of(CHAT_PLATFORM_MICROSOFT_TEAMS)

    # -- receive ---------------------------------------------------------------

    def parse_message(self, payload: Mapping[str, Any]) -> InboundMessage | None:
        """Return what ``payload`` says, or ``None`` if it says nothing to this bot."""
        return app.parse_message(payload, bot_id=self.bot_id)

    def parse_decision(self, payload: Mapping[str, Any]) -> InteractionDecision | None:
        """Return the interaction decision ``payload`` carries, or ``None``."""
        return app.parse_decision(payload)

    def user_of(self, payload: Mapping[str, Any]) -> PlatformUser | None:
        """Return the Teams user ``payload`` was produced by, or ``None``."""
        return app.user_of(payload)

    async def thread_history(self, target: ChatTarget, *, limit: int) -> Sequence[ThreadMessage]:
        """Return up to ``limit`` earlier activities of ``target``, oldest first."""
        reply = await self.api.conversation_activities(_reference(target), limit=limit)
        raw = reply.document.get("activities")
        if not isinstance(raw, list):
            return ()
        return tuple(
            ThreadMessage(
                author=_author(activity),
                text=app.strip_mentions(str(activity.get("text") or "")),
                posted_at=str(activity.get("timestamp") or ""),
                is_bot=_author_id(activity) == self.bot_id,
            )
            for activity in raw
            if isinstance(activity, Mapping)
        )

    # -- stream ----------------------------------------------------------------

    async def post(self, target: ChatTarget, text: str) -> PostedMessage:
        """Post ``text`` to ``target`` and return the activity that now exists."""
        reply = await self.api.send_activity(_reference(target), text=text)
        return PostedMessage(target=target, message_id=activity_id_of(reply), text=text)

    async def edit(self, message: PostedMessage, text: str) -> PostedMessage:
        """Rewrite ``message``'s activity in place."""
        await self.api.update_activity(_reference(message.target), message.message_id, text=text)
        return message.with_text(text)

    async def attach(self, target: ChatTarget, attachment: Attachment) -> PostedMessage:
        """Deliver ``attachment`` as a card carrying the whole report.

        Teams file upload needs a consent flow per user, which an incident is
        not the moment for, so a long report arrives as a card instead. It is
        still one addressable message holding the whole text, which is what a
        report that must not be truncated needs.
        """
        reply = await self.api.send_activity(
            _reference(target),
            text=attachment.title or attachment.filename,
            attachments=[
                cards.attachment_of(
                    cards.report_card(attachment.title or attachment.filename, attachment.content)
                )
            ],
        )
        posted = activity_id_of(reply)
        if not posted:
            raise ChatUnavailable(CHAT_PLATFORM_MICROSOFT_TEAMS, "the card was not accepted")
        return PostedMessage(target=target, message_id=posted, text=attachment.content)

    # -- render an interaction -------------------------------------------------

    def render_interaction(self, interaction: Interaction) -> InteractiveElement:
        """Return the Adaptive Card ``interaction`` is decided with."""
        return cards.render(interaction)

    async def send_interaction(
        self, target: ChatTarget, element: InteractiveElement
    ) -> PostedMessage:
        """Show ``element`` in ``target`` and return the activity carrying it."""
        card = element.payload.get("card")
        reply = await self.api.send_activity(
            _reference(target),
            text=element.fallback_text,
            attachments=[cards.attachment_of(card)] if isinstance(card, Mapping) else (),
        )
        return PostedMessage(
            target=target, message_id=activity_id_of(reply), text=element.fallback_text
        )

    async def close_interaction(self, message: PostedMessage, event: InteractionEvent) -> None:
        """Replace ``message``'s card actions with the outcome ``event`` records."""
        card, text = cards.closed_card(event)
        await self.api.update_activity(
            _reference(message.target),
            message.message_id,
            text=text,
            attachments=[cards.attachment_of(card)],
        )


def _reference(target: ChatTarget) -> ConversationReference:
    """Return the conversation reference ``target`` addresses."""
    conversation = (
        f"{target.channel_id}{THREAD_SEPARATOR}{target.thread_id}"
        if target.thread_id and target.thread_id != target.channel_id
        else target.channel_id
    )
    return ConversationReference(conversation_id=conversation, tenant_id=target.workspace_id)


def _author(activity: Mapping[str, Any]) -> str:
    """Return the display name of whoever sent ``activity``."""
    sender = activity.get("from")
    if not isinstance(sender, Mapping):
        return "unknown"
    return str(sender.get("name") or sender.get("id") or "unknown")


def _author_id(activity: Mapping[str, Any]) -> str:
    """Return the identifier of whoever sent ``activity``."""
    sender = activity.get("from")
    return str(sender.get("id") or "") if isinstance(sender, Mapping) else ""


__all__ = ["TeamsPlatform"]
