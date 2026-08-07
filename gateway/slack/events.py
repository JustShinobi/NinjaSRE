"""Reading a Slack payload: who said what, where, and whether it was to this bot.

Three shapes arrive on the same wire and mean different things, so each is
recognised explicitly rather than by looking for fields that happen to be
present. An ``app_mention`` starts something. A ``message`` in a thread the bot
is already in continues it. A slash command is a command, and it arrives with no
``event`` wrapper at all because Slack posts it as a form.

**Thread binding is ``thread_ts`` or ``ts``.** A reply carries ``thread_ts``; the
first message of a thread carries only ``ts``, and that same value becomes the
thread's identifier the moment anything replies to it. Reading it the other way
round — assuming ``thread_ts`` is always present — is how a mention in a channel
ends up starting a run bound to nothing.

**The bot's own messages are ignored.** Not as a nicety: a bot that reads its own
posts as inbound context is one that talks to itself for as long as the thread
stays open.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Final

from config.constants.surfaces import CHAT_PLATFORM_SLACK
from gateway.chat.commands import SLACK_COMMAND, parse
from gateway.chat.port import ChatTarget, InboundMessage, InteractionDecision, PlatformUser

#: ``<@U123ABC>`` — the token Slack substitutes for a mention. Stripped from the
#: text so an objective reads as a sentence rather than as markup.
MENTION = re.compile(r"<@([A-Z0-9]+)(\|[^>]+)?>")

#: The prefix every interactive element this bot builds carries, so a payload
#: from another app's block in the same message is not read as ours.
ACTION_PREFIX: Final = "ninjasre:"


def target_of(event: Mapping[str, Any], team_id: str) -> ChatTarget:
    """Return where ``event`` happened, bound to its thread."""
    thread = str(event.get("thread_ts") or event.get("ts") or "")
    return ChatTarget(
        platform=CHAT_PLATFORM_SLACK,
        channel_id=str(event.get("channel") or event.get("channel_id") or ""),
        thread_id=thread,
        workspace_id=team_id,
    )


def user_of(payload: Mapping[str, Any]) -> PlatformUser | None:
    """Return who produced ``payload``, whichever of the three shapes it is."""
    team = _team_of(payload)

    event = payload.get("event")
    if isinstance(event, Mapping):
        user_id = str(event.get("user") or "")
        return _user(user_id, team) if user_id else None

    who = payload.get("user")
    if isinstance(who, Mapping):
        return _user(str(who.get("id") or ""), team, display_name=str(who.get("username") or ""))

    command_user = str(payload.get("user_id") or "")
    if command_user:
        return _user(command_user, team, display_name=str(payload.get("user_name") or ""))
    return None


def _user(user_id: str, team: str, *, display_name: str = "") -> PlatformUser | None:
    return (
        PlatformUser(
            platform=CHAT_PLATFORM_SLACK,
            user_id=user_id,
            display_name=display_name,
            workspace_id=team,
        )
        if user_id
        else None
    )


def _team_of(payload: Mapping[str, Any]) -> str:
    """Return the workspace ``payload`` came from, wherever it put it."""
    team = payload.get("team")
    if isinstance(team, Mapping):
        return str(team.get("id") or "")
    return str(payload.get("team_id") or "")


def parse_message(payload: Mapping[str, Any], *, bot_user_id: str) -> InboundMessage | None:
    """Return what ``payload`` says, or ``None`` if it says nothing to this bot."""
    if "command" in payload:
        return _slash_command(payload)

    event = payload.get("event")
    if not isinstance(event, Mapping):
        return None
    kind = str(event.get("type") or "")
    if kind not in {"app_mention", "message"}:
        return None
    if event.get("bot_id") or str(event.get("user") or "") == bot_user_id:
        return None
    if event.get("subtype"):
        # An edit, a join, a file share. None of them is somebody asking for
        # something, and treating them as messages produces duplicate runs.
        return None

    user = user_of(payload)
    if user is None:
        return None

    raw = str(event.get("text") or "")
    addressed = kind == "app_mention" or f"<@{bot_user_id}>" in raw
    text = MENTION.sub("", raw).strip()
    command, arguments = parse(text)

    return InboundMessage(
        target=target_of(event, _team_of(payload)),
        user=user,
        text=text,
        addressed=addressed,
        command=command,
        arguments=arguments,
        message_id=str(event.get("ts") or ""),
    )


def _slash_command(payload: Mapping[str, Any]) -> InboundMessage | None:
    """Return the command a Slack slash invocation carries.

    Slack registers one command per app, so the catalogue's names arrive as its
    first argument: ``/ninjasre approve i-1``.
    """
    user = user_of(payload)
    if user is None:
        return None
    if str(payload.get("command") or "") != SLACK_COMMAND:
        return None

    body = str(payload.get("text") or "").strip()
    head, _, rest = body.partition(" ")
    command, arguments = parse(f"/{head}" if head else "/help")

    return InboundMessage(
        target=ChatTarget(
            platform=CHAT_PLATFORM_SLACK,
            channel_id=str(payload.get("channel_id") or ""),
            thread_id=str(payload.get("thread_ts") or ""),
            workspace_id=_team_of(payload),
        ),
        user=user,
        text=body,
        addressed=True,
        command=command or "help",
        arguments=(arguments or rest).strip(),
        message_id=str(payload.get("trigger_id") or ""),
    )


def parse_decision(payload: Mapping[str, Any]) -> InteractionDecision | None:
    """Return the decision a Block Kit interaction payload carries, or ``None``."""
    if str(payload.get("type") or "") != "block_actions":
        return None
    actions = payload.get("actions")
    if not isinstance(actions, list) or not actions:
        return None
    action = actions[0]
    if not isinstance(action, Mapping):
        return None
    action_id = str(action.get("action_id") or "")
    if not action_id.startswith(ACTION_PREFIX):
        return None

    user = user_of(payload)
    if user is None:
        return None

    channel = payload.get("channel")
    message = payload.get("message")
    return InteractionDecision(
        interaction_id=action_id[len(ACTION_PREFIX) :],
        user=user,
        choice=str(action.get("value") or ""),
        target=ChatTarget(
            platform=CHAT_PLATFORM_SLACK,
            channel_id=str(channel.get("id") or "") if isinstance(channel, Mapping) else "",
            thread_id=(
                str(message.get("thread_ts") or message.get("ts") or "")
                if isinstance(message, Mapping)
                else ""
            ),
            workspace_id=_team_of(payload),
        ),
        element_id=str(message.get("ts") or "") if isinstance(message, Mapping) else "",
        text=str(action.get("value") or ""),
    )


def joined_channel(payload: Mapping[str, Any], *, bot_user_id: str) -> str:
    """Return the channel this bot was just invited to, or the empty string."""
    event = payload.get("event")
    if not isinstance(event, Mapping):
        return ""
    if str(event.get("type") or "") != "member_joined_channel":
        return ""
    if not bot_user_id or str(event.get("user") or "") != bot_user_id:
        return ""
    return str(event.get("channel") or "")


__all__ = [
    "ACTION_PREFIX",
    "MENTION",
    "joined_channel",
    "parse_decision",
    "parse_message",
    "target_of",
    "user_of",
]
