"""The Discord REST calls this surface makes, and how a thread is created.

Discord threads are first-class channels: replying "in a thread" means creating
one from a message and then posting into it by its own id, which is why
``start_thread`` exists and why a ``ChatTarget``'s ``thread_id`` is the channel
posts actually go to.

There is no token in this module and no parameter that could hold one: the bot
token is injected by the credential proxy at the network edge.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from gateway.chat.port import ChatTransport, PlatformCall, PlatformReply

#: The integration name the credential proxy resolves the bot token under.
DISCORD_INTEGRATION: Final = "discord"

#: Discord's REST API version this adapter speaks. Pinned: Discord retires
#: versions on a schedule, and an unpinned client breaks on their timetable.
API_VERSION: Final = "v10"

#: How long a thread created for an investigation stays warm before Discord
#: archives it. A day: long enough for an incident and its post-mortem chatter,
#: short enough that a guild's thread list stays usable.
THREAD_AUTO_ARCHIVE_MINUTES: Final = 1_440

#: Discord's component types, as the two this surface uses.
ACTION_ROW: Final = 1
BUTTON: Final = 2


@dataclass(frozen=True, slots=True)
class DiscordApi:
    """The Discord REST API, as the calls this surface actually makes."""

    transport: ChatTransport
    application_id: str = ""

    async def create_message(
        self,
        *,
        channel_id: str,
        content: str,
        components: Sequence[Mapping[str, Any]] = (),
    ) -> PlatformReply:
        """Post a message into a channel or a thread."""
        payload: dict[str, Any] = {"content": content}
        if components:
            payload["components"] = list(components)
        return await self.transport.send(
            PlatformCall(
                method="POST",
                path=f"{API_VERSION}/channels/{channel_id}/messages",
                payload=payload,
            )
        )

    async def edit_message(
        self,
        *,
        channel_id: str,
        message_id: str,
        content: str,
        components: Sequence[Mapping[str, Any]] = (),
    ) -> PlatformReply:
        """Rewrite a message in place, which is how progress streams."""
        # ``components`` is always sent, even empty: Discord keeps the existing
        # components when the field is absent, so a decided approval would keep
        # its buttons.
        return await self.transport.send(
            PlatformCall(
                method="PATCH",
                path=f"{API_VERSION}/channels/{channel_id}/messages/{message_id}",
                payload={"content": content, "components": list(components)},
            )
        )

    async def create_attachment(
        self, *, channel_id: str, filename: str, content: str, title: str = ""
    ) -> PlatformReply:
        """Deliver a long report as a file rather than as a wall of messages."""
        return await self.transport.send(
            PlatformCall(
                method="POST",
                path=f"{API_VERSION}/channels/{channel_id}/messages",
                payload={
                    "content": title or filename,
                    "files": [{"filename": filename, "content": content}],
                },
            )
        )

    async def start_thread(self, *, channel_id: str, message_id: str, name: str) -> PlatformReply:
        """Open a thread from a message, which is where an investigation runs."""
        return await self.transport.send(
            PlatformCall(
                method="POST",
                path=f"{API_VERSION}/channels/{channel_id}/messages/{message_id}/threads",
                payload={"name": name[:100], "auto_archive_duration": THREAD_AUTO_ARCHIVE_MINUTES},
            )
        )

    async def channel_messages(self, *, channel_id: str, limit: int) -> PlatformReply:
        """Return a channel's recent messages, newest first as Discord orders them."""
        return await self.transport.send(
            PlatformCall(
                method="GET",
                path=f"{API_VERSION}/channels/{channel_id}/messages",
                query={"limit": str(limit)},
            )
        )

    async def register_commands(
        self, commands: Sequence[Mapping[str, Any]], *, guild_id: str = ""
    ) -> PlatformReply:
        """Register the shared catalogue as this application's commands.

        Guild-scoped when a guild is named — those take effect immediately —
        and global otherwise, which Discord propagates over about an hour.
        """
        scope = f"guilds/{guild_id}/commands" if guild_id else "commands"
        return await self.transport.send(
            PlatformCall(
                method="PUT",
                path=f"{API_VERSION}/applications/{self.application_id}/{scope}",
                payload={"commands": list(commands)},
            )
        )

    async def acknowledge_interaction(
        self, *, interaction_id: str, token: str, kind: int = 6
    ) -> PlatformReply:
        """Acknowledge an interaction inside Discord's three-second window.

        ``token`` is the interaction's own single-use continuation token, which
        Discord sends on the inbound event. It is not a credential this
        deployment holds — it arrives with the request and dies with it.
        """
        return await self.transport.send(
            PlatformCall(
                method="POST",
                path=f"{API_VERSION}/interactions/{interaction_id}/{token}/callback",
                payload={"type": kind},
            )
        )


def message_id_of(reply: PlatformReply) -> str:
    """Return the snowflake a Discord reply carries."""
    return str(reply.document.get("id", ""))


__all__ = [
    "ACTION_ROW",
    "API_VERSION",
    "BUTTON",
    "DISCORD_INTEGRATION",
    "THREAD_AUTO_ARCHIVE_MINUTES",
    "DiscordApi",
    "message_id_of",
]
