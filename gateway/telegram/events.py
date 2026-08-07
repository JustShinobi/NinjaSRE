"""Reading a Telegram update: group chats, direct chats, and callback queries.

A group and a direct chat differ in one way that matters: in a group the bot
only reads what is addressed to it, and in a direct chat there is nobody else to
address. Requiring an ``@mention`` in a one-to-one chat would mean the
bot ignored everything said to it.

**A thread is a forum topic, or the message being replied to.** Telegram's
threading is newer than its message model, so a supergroup with topics enabled
carries ``message_thread_id`` and everything else carries ``reply_to_message``.
Both are read, in that order, because a topic is the stronger binding.

**A callback query's data is the whole payload.** Telegram allows 64 bytes and
no more, so the interaction id and the choice are packed into it rather than
looked up — a server-side map keyed by button would be state that outlives the
process that made it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from config.constants.surfaces import CHAT_PLATFORM_TELEGRAM
from gateway.chat.commands import parse
from gateway.chat.port import ChatTarget, InboundMessage, InteractionDecision, PlatformUser

#: The prefix every callback this bot builds carries, so another bot's button in
#: the same chat is not read as ours.
CALLBACK_PREFIX: Final = "ninjasre:"

#: Telegram's own ceiling on callback data. Exceeding it makes the button fail
#: silently at send time, which is the worst way for an approval to not work.
MAX_CALLBACK_BYTES: Final = 64

#: The chat types that are one-to-one, and therefore addressed by definition.
DIRECT_CHAT_TYPES: Final[frozenset[str]] = frozenset({"private"})


def callback_data(interaction_id: str, choice: str) -> str:
    """Return the callback payload a button carries.

    Raises:
        ValueError: the packed value is past Telegram's 64-byte ceiling.
    """
    packed = f"{CALLBACK_PREFIX}{interaction_id}:{choice}"
    if len(packed.encode("utf-8")) > MAX_CALLBACK_BYTES:
        raise ValueError(
            f"{packed!r} is longer than Telegram's {MAX_CALLBACK_BYTES}-byte callback "
            f"limit, and a button built from it would fail silently"
        )
    return packed


def user_of(payload: Mapping[str, Any]) -> PlatformUser | None:
    """Return who produced ``payload``, whichever kind of update it is."""
    holder = payload.get("message") or payload.get("callback_query") or payload
    if not isinstance(holder, Mapping):
        return None
    sender = holder.get("from")
    if not isinstance(sender, Mapping):
        return None
    user_id = str(sender.get("id") or "")
    if not user_id:
        return None
    return PlatformUser(
        platform=CHAT_PLATFORM_TELEGRAM,
        user_id=user_id,
        display_name=str(sender.get("username") or sender.get("first_name") or ""),
        workspace_id=_chat_id(holder),
    )


def _chat_id(holder: Mapping[str, Any]) -> str:
    """Return the chat a message or callback belongs to."""
    message = holder if "chat" in holder else holder.get("message")
    if not isinstance(message, Mapping):
        return ""
    chat = message.get("chat")
    return str(chat.get("id") or "") if isinstance(chat, Mapping) else ""


def target_of(message: Mapping[str, Any]) -> ChatTarget:
    """Return where ``message`` was posted, bound to its thread."""
    chat = message.get("chat")
    chat_id = str(chat.get("id") or "") if isinstance(chat, Mapping) else ""
    return ChatTarget(
        platform=CHAT_PLATFORM_TELEGRAM,
        channel_id=chat_id,
        thread_id=_thread_of(message),
        workspace_id=chat_id,
    )


def _thread_of(message: Mapping[str, Any]) -> str:
    """Return the topic or the replied-to message, whichever this thread is."""
    topic = message.get("message_thread_id")
    if topic:
        return str(topic)
    replied = message.get("reply_to_message")
    if isinstance(replied, Mapping) and replied.get("message_id"):
        return str(replied["message_id"])
    return ""


def _addressed(message: Mapping[str, Any], bot_username: str) -> bool:
    """Return whether ``message`` was addressed to this bot."""
    chat = message.get("chat")
    kind = str(chat.get("type") or "") if isinstance(chat, Mapping) else ""
    if kind in DIRECT_CHAT_TYPES:
        return True
    text = str(message.get("text") or "")
    return bool(bot_username) and f"@{bot_username}" in text


def parse_message(payload: Mapping[str, Any], *, bot_username: str) -> InboundMessage | None:
    """Return what ``payload`` says, or ``None`` if it says nothing to this bot."""
    message = payload.get("message") or payload.get("channel_post")
    if not isinstance(message, Mapping):
        return None
    sender = message.get("from")
    if isinstance(sender, Mapping) and sender.get("is_bot"):
        return None

    user = user_of(payload)
    if user is None:
        return None

    raw = str(message.get("text") or "")
    text = raw.replace(f"@{bot_username}", "").strip() if bot_username else raw.strip()
    command, arguments = parse(raw.strip())

    return InboundMessage(
        target=target_of(message),
        user=user,
        text=text,
        addressed=_addressed(message, bot_username),
        command=command,
        arguments=arguments,
        message_id=str(message.get("message_id") or ""),
    )


def parse_decision(payload: Mapping[str, Any]) -> InteractionDecision | None:
    """Return the decision a callback query carries, or ``None``."""
    query = payload.get("callback_query")
    if not isinstance(query, Mapping):
        return None
    data = str(query.get("data") or "")
    if not data.startswith(CALLBACK_PREFIX):
        return None
    interaction_id, _, choice = data[len(CALLBACK_PREFIX) :].partition(":")
    if not interaction_id:
        return None

    user = user_of(payload)
    if user is None:
        return None

    message = query.get("message")
    return InteractionDecision(
        interaction_id=interaction_id,
        user=user,
        choice=choice,
        target=target_of(message)
        if isinstance(message, Mapping)
        else ChatTarget(platform=CHAT_PLATFORM_TELEGRAM, channel_id=""),
        element_id=str(message.get("message_id") or "") if isinstance(message, Mapping) else "",
        text=choice,
    )


def callback_query_id(payload: Mapping[str, Any]) -> str:
    """Return the callback id that has to be acknowledged, or the empty string."""
    query = payload.get("callback_query")
    return str(query.get("id") or "") if isinstance(query, Mapping) else ""


__all__ = [
    "CALLBACK_PREFIX",
    "DIRECT_CHAT_TYPES",
    "MAX_CALLBACK_BYTES",
    "callback_data",
    "callback_query_id",
    "parse_decision",
    "parse_message",
    "target_of",
    "user_of",
]
