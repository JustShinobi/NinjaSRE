"""Reading a Discord gateway event: mentions, application commands, components.

Discord multiplexes everything through one socket and distinguishes by ``t``:
``MESSAGE_CREATE`` for what people type, ``INTERACTION_CREATE`` for both slash
commands and button presses. The second is subdivided by a numeric ``type``,
which is why those numbers are named here rather than written at the branch.

**A guild member and a direct-message author are in different places.** In a
guild the author is under ``member.user``; in a DM it is under ``author``. Both
are read, because a bot that only handled the guild case would ignore every
direct message silently.

**The bot's own messages are ignored**, and so are other bots'. A room with two
assistants in it is otherwise a room where they answer each other.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from config.constants.surfaces import CHAT_PLATFORM_DISCORD
from gateway.chat.commands import parse
from gateway.chat.port import ChatTarget, InboundMessage, InteractionDecision, PlatformUser

#: The prefix every component this bot builds carries, so another app's button
#: in the same channel is not read as ours.
COMPONENT_PREFIX: Final = "ninjasre:"

#: Discord's ``custom_id`` ceiling. A component built past it is rejected at
#: send time, which is the worst moment for an approval to not appear.
MAX_CUSTOM_ID_CHARS: Final = 100

#: Interaction types, as the two this surface handles.
APPLICATION_COMMAND: Final = 2
MESSAGE_COMPONENT: Final = 3


def custom_id(interaction_id: str, choice: str) -> str:
    """Return the ``custom_id`` a button carries.

    Raises:
        ValueError: the packed value is past Discord's 100-character ceiling.
    """
    packed = f"{COMPONENT_PREFIX}{interaction_id}:{choice}"
    if len(packed) > MAX_CUSTOM_ID_CHARS:
        raise ValueError(
            f"{packed!r} is longer than Discord's {MAX_CUSTOM_ID_CHARS}-character "
            f"custom_id limit, and a component built from it would be rejected"
        )
    return packed


def _body(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return the event body, whether or not it is still in its gateway envelope."""
    data = payload.get("d")
    return data if isinstance(data, Mapping) else payload


def user_of(payload: Mapping[str, Any]) -> PlatformUser | None:
    """Return who produced ``payload``, from either the guild or the DM shape."""
    body = _body(payload)
    member = body.get("member")
    raw = member.get("user") if isinstance(member, Mapping) else None
    if not isinstance(raw, Mapping):
        raw = body.get("author") if isinstance(body.get("author"), Mapping) else None
    if not isinstance(raw, Mapping):
        return None
    user_id = str(raw.get("id") or "")
    if not user_id:
        return None
    return PlatformUser(
        platform=CHAT_PLATFORM_DISCORD,
        user_id=user_id,
        display_name=str(raw.get("global_name") or raw.get("username") or ""),
        workspace_id=str(body.get("guild_id") or ""),
    )


def target_of(body: Mapping[str, Any]) -> ChatTarget:
    """Return where ``body`` happened, bound to its thread.

    A message inside a thread carries that thread as its ``channel_id`` — the
    thread *is* a channel — so both fields hold it. That is what makes a bound
    thread's key stable whether the event named the thread or the parent.
    """
    channel = str(body.get("channel_id") or "")
    thread = body.get("thread")
    thread_id = (
        str(thread.get("id") or "") if isinstance(thread, Mapping) else str(body.get("id") or "")
    )
    return ChatTarget(
        platform=CHAT_PLATFORM_DISCORD,
        channel_id=channel,
        thread_id=thread_id if isinstance(thread, Mapping) else "",
        workspace_id=str(body.get("guild_id") or ""),
    )


def parse_message(payload: Mapping[str, Any], *, application_id: str) -> InboundMessage | None:
    """Return what ``payload`` says, or ``None`` if it says nothing to this bot."""
    kind = str(payload.get("t") or "")
    body = _body(payload)

    if kind == "INTERACTION_CREATE" or body.get("type") in {APPLICATION_COMMAND}:
        return _application_command(body)
    if kind and kind != "MESSAGE_CREATE":
        return None
    if "content" not in body:
        return None

    author = body.get("author")
    if isinstance(author, Mapping) and (
        author.get("bot") or str(author.get("id") or "") == application_id
    ):
        return None

    user = user_of(payload)
    if user is None:
        return None

    raw = str(body.get("content") or "")
    text = _strip_mention(raw, application_id)
    command, arguments = parse(text)

    return InboundMessage(
        target=target_of(body),
        user=user,
        text=text,
        addressed=_mentions(body, application_id),
        command=command,
        arguments=arguments,
        message_id=str(body.get("id") or ""),
    )


def _application_command(body: Mapping[str, Any]) -> InboundMessage | None:
    """Return the command a slash invocation carries, or ``None``."""
    if body.get("type") != APPLICATION_COMMAND:
        return None
    data = body.get("data")
    if not isinstance(data, Mapping):
        return None
    name = str(data.get("name") or "")
    command, _ = parse(f"/{name}")
    if not command:
        return None

    user = user_of(body)
    if user is None:
        return None

    return InboundMessage(
        target=target_of(body),
        user=user,
        text=name,
        addressed=True,
        command=command,
        arguments=_option_text(data),
        message_id=str(body.get("id") or ""),
    )


def _option_text(data: Mapping[str, Any]) -> str:
    """Return the free-text argument an application command carried."""
    options = data.get("options")
    if not isinstance(options, list):
        return ""
    for option in options:
        if isinstance(option, Mapping) and isinstance(option.get("value"), str):
            return str(option["value"])
    return ""


def _mentions(body: Mapping[str, Any], application_id: str) -> bool:
    """Return whether this bot was mentioned in ``body``."""
    if not application_id:
        return False
    mentioned = body.get("mentions")
    if isinstance(mentioned, list):
        for who in mentioned:
            if isinstance(who, Mapping) and str(who.get("id") or "") == application_id:
                return True
    return f"<@{application_id}>" in str(body.get("content") or "")


def _strip_mention(text: str, application_id: str) -> str:
    """Return ``text`` with this bot's mention token removed."""
    if not application_id:
        return text.strip()
    return text.replace(f"<@{application_id}>", "").replace(f"<@!{application_id}>", "").strip()


def parse_decision(payload: Mapping[str, Any]) -> InteractionDecision | None:
    """Return the decision a message-component interaction carries, or ``None``."""
    body = _body(payload)
    if body.get("type") != MESSAGE_COMPONENT:
        return None
    data = body.get("data")
    if not isinstance(data, Mapping):
        return None
    identifier = str(data.get("custom_id") or "")
    if not identifier.startswith(COMPONENT_PREFIX):
        return None
    interaction_id, _, choice = identifier[len(COMPONENT_PREFIX) :].partition(":")
    if not interaction_id:
        return None

    user = user_of(payload)
    if user is None:
        return None

    message = body.get("message")
    return InteractionDecision(
        interaction_id=interaction_id,
        user=user,
        choice=choice,
        target=target_of(body),
        element_id=str(message.get("id") or "") if isinstance(message, Mapping) else "",
        text=choice,
    )


def acknowledgement_of(payload: Mapping[str, Any]) -> tuple[str, str]:
    """Return the ``(interaction id, token)`` an inbound interaction has to be acked with."""
    body = _body(payload)
    return str(body.get("id") or ""), str(body.get("token") or "")


__all__ = [
    "APPLICATION_COMMAND",
    "COMPONENT_PREFIX",
    "MAX_CUSTOM_ID_CHARS",
    "MESSAGE_COMPONENT",
    "acknowledgement_of",
    "custom_id",
    "parse_decision",
    "parse_message",
    "target_of",
    "user_of",
]
