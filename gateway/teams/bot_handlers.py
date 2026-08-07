"""The Bot Framework calls this surface makes, and nothing about authentication.

Teams replies by posting an activity to the conversation's own service URL, so
every call here takes the conversation reference the inbound activity carried.
There is no token in this module and no parameter that could hold one: the bot's
credential is injected by the credential proxy at the network edge.

``updateActivity`` is what makes in-place streaming work on Teams. It is a
``PUT`` to the activity's own path, which is why a posted activity's id is
carried around rather than only its conversation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from gateway.chat.port import ChatTransport, PlatformCall, PlatformReply
from gateway.teams.app import ConversationReference

#: The integration name the credential proxy resolves the bot credential under.
TEAMS_INTEGRATION: Final = "microsoft_teams"

#: The Bot Framework's conversations API, relative to a tenant's service URL.
CONVERSATIONS_PATH: Final = "v3/conversations"


@dataclass(frozen=True, slots=True)
class TeamsApi:
    """The four Bot Framework calls this surface makes."""

    transport: ChatTransport

    async def send_activity(
        self,
        reference: ConversationReference,
        *,
        text: str = "",
        attachments: Sequence[Mapping[str, Any]] = (),
    ) -> PlatformReply:
        """Post an activity into ``reference``'s conversation."""
        return await self.transport.send(
            PlatformCall(
                method="POST",
                path=f"{CONVERSATIONS_PATH}/{reference.conversation_id}/activities",
                payload=_activity(reference, text=text, attachments=attachments),
            )
        )

    async def update_activity(
        self,
        reference: ConversationReference,
        activity_id: str,
        *,
        text: str = "",
        attachments: Sequence[Mapping[str, Any]] = (),
    ) -> PlatformReply:
        """Rewrite an activity in place, which is how a card streams."""
        return await self.transport.send(
            PlatformCall(
                method="PUT",
                path=f"{CONVERSATIONS_PATH}/{reference.conversation_id}/activities/{activity_id}",
                payload=_activity(reference, text=text, attachments=attachments),
            )
        )

    async def conversation_activities(
        self, reference: ConversationReference, *, limit: int
    ) -> PlatformReply:
        """Return earlier activities of this conversation, oldest first."""
        return await self.transport.send(
            PlatformCall(
                method="GET",
                path=f"{CONVERSATIONS_PATH}/{reference.conversation_id}/activities",
                query={"limit": str(limit)},
            )
        )

    async def member(self, reference: ConversationReference, user_id: str) -> PlatformReply:
        """Return what Teams knows about one conversation member.

        The identity flow's one call: it answers with the member's Azure AD
        object id and their UPN, which is what a mapping is keyed on when an
        operator maps by account rather than by Teams user id.
        """
        return await self.transport.send(
            PlatformCall(
                method="GET",
                path=f"{CONVERSATIONS_PATH}/{reference.conversation_id}/members/{user_id}",
            )
        )


def _activity(
    reference: ConversationReference,
    *,
    text: str,
    attachments: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    """Return the activity envelope a reply is sent as."""
    activity: dict[str, Any] = {"type": "message", "text": text}
    if attachments:
        activity["attachments"] = list(attachments)
    if reference.activity_id:
        activity["replyToId"] = reference.activity_id
    return activity


def activity_id_of(reply: PlatformReply) -> str:
    """Return the id a posted activity answered with."""
    return str(reply.document.get("id", ""))


__all__ = [
    "CONVERSATIONS_PATH",
    "TEAMS_INTEGRATION",
    "TeamsApi",
    "activity_id_of",
]
