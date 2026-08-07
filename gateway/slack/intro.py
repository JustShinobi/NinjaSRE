"""One introduction per channel this bot is invited to.

The three things people otherwise discover by trial and error: mention it to
start, it follows the thread afterwards without being re-tagged, and anything
that writes asks first. All three are surprises in the wrong direction if you
find them out during an incident.

**Greeted once, per process.** The set is a spam guard rather than a record —
being re-invited after a restart greets again, which is the right failure: a
channel greeted twice is mildly noisy, and a channel never greeted has three
behaviours nobody knows about.

**A failed post is not remembered as greeted.** Otherwise the one channel where
the introduction mattered is the one that never gets it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from gateway.chat.commands import COMMAND_CATALOGUE, SLACK_COMMAND
from gateway.chat.port import ChatTarget, ChatUnavailable
from gateway.slack import events
from gateway.slack.output_sink import SlackPlatform
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: Rejoining a channel after this many others were greeted may greet again. The
#: bound exists so a long-lived process cannot grow this set without limit.
MAX_GREETED_CHANNELS: Final = 1_024


def introduction(bot_user_id: str) -> str:
    """Return what a channel is told when this bot joins it."""
    me = f"<@{bot_user_id}>" if bot_user_id else "this bot"
    commands = ", ".join(f"`{command.name}`" for command in COMMAND_CATALOGUE[:4])
    return "\n".join(
        (
            f"Hi — I'm {me}, an SRE teammate.",
            f"• Mention {me} with a question or an incident and I'll investigate in a "
            "thread, streaming what I'm doing as I go.",
            f"• Once I'm in a thread I follow the conversation — no need to tag {me} "
            "on every message.",
            "• Anything that changes production asks for approval first, and shows you "
            "the change, its blast radius, and how it is rolled back.",
            f"• `{SLACK_COMMAND}` takes {commands} and more; `{SLACK_COMMAND} help` "
            "lists everything.",
            "• Acting on an approval needs a NinjaSRE account mapped to your Slack "
            "user. Ask an operator if you don't have one yet.",
        )
    )


@dataclass(slots=True)
class ChannelIntroducer:
    """Posts the introduction the first time this bot joins each channel."""

    platform: SlackPlatform
    bot_user_id: str = ""
    _greeted: set[str] = field(default_factory=set, init=False, repr=False)

    @property
    def greeted(self) -> tuple[str, ...]:
        """Return the channels already introduced to, in no particular order."""
        return tuple(sorted(self._greeted))

    async def handle(self, payload: Mapping[str, Any]) -> bool:
        """Greet if ``payload`` is this bot joining a channel. Return whether it did."""
        channel_id = events.joined_channel(payload, bot_user_id=self.bot_user_id)
        if not channel_id or not self._claim(channel_id):
            return False

        target = ChatTarget(
            platform=self.platform.name,
            channel_id=channel_id,
            workspace_id=_team_of(payload),
        )
        try:
            await self.platform.post(target, introduction(self.bot_user_id))
        except ChatUnavailable as gone:
            # Let the next join event retry rather than staying silent for ever.
            self._greeted.discard(channel_id)
            logger.warning("slack.intro_failed", channel_id=channel_id, reason=gone.reason)
            return False
        logger.info("slack.intro_posted", channel_id=channel_id)
        return True

    def _claim(self, channel_id: str) -> bool:
        """Return whether this call is the one that greets ``channel_id``."""
        if channel_id in self._greeted:
            return False
        if len(self._greeted) >= MAX_GREETED_CHANNELS:
            self._greeted.clear()
        self._greeted.add(channel_id)
        return True


def _team_of(payload: Mapping[str, Any]) -> str:
    """Return the workspace ``payload`` came from."""
    return str(payload.get("team_id") or "")


__all__ = [
    "MAX_GREETED_CHANNELS",
    "ChannelIntroducer",
    "introduction",
]
