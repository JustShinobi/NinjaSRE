"""Bot Framework wiring: a channel conversation and a direct message, one path.

Teams delivers everything as an *activity* — a message, a card submission, a
member joining, a typing indicator — on one endpoint, and the conversation type
is what distinguishes a channel post from a one-to-one chat. Both are
served, and they differ here in exactly one respect: a channel conversation has
a thread inside it and a personal one does not, so a personal chat's thread is
the conversation itself.

**The service URL belongs to the conversation, not to the deployment.** Teams
tells the bot where to reply on each activity, and it varies by tenant and by
cloud. Storing one globally is how a multi-tenant install starts replying into
the wrong tenant's service, so it travels with the conversation reference.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from config.constants.surfaces import CHAT_PLATFORM_MICROSOFT_TEAMS
from gateway.chat.commands import parse
from gateway.chat.port import ChatTarget, InboundMessage, InteractionDecision, PlatformUser

#: Teams splits a channel conversation id as ``<channel>;messageid=<root>``. The
#: part after the separator is the thread, and it is absent for the first
#: message of a new one.
THREAD_SEPARATOR: Final = ";messageid="

#: Activity types this surface acts on. Everything else — typing, reactions,
#: membership churn — is acknowledged and ignored.
MESSAGE_ACTIVITY: Final = "message"
INVOKE_ACTIVITY: Final = "invoke"
CARD_ACTION: Final = "adaptiveCard/action"

CONVERSATION_PERSONAL: Final = "personal"


@dataclass(frozen=True, slots=True)
class ConversationReference:
    """Where a reply goes, as Teams describes it on every inbound activity."""

    conversation_id: str
    service_url: str = ""
    tenant_id: str = ""
    activity_id: str = ""

    @property
    def channel_id(self) -> str:
        """Return the channel half of a conversation id."""
        return self.conversation_id.split(THREAD_SEPARATOR, 1)[0]

    @property
    def thread_id(self) -> str:
        """Return the thread half, or the empty string for a new conversation."""
        _, separator, thread = self.conversation_id.partition(THREAD_SEPARATOR)
        return thread if separator else ""


def reference_of(activity: Mapping[str, Any]) -> ConversationReference:
    """Return where a reply to ``activity`` goes."""
    conversation = activity.get("conversation")
    channel_data = activity.get("channelData")
    tenant = channel_data.get("tenant") if isinstance(channel_data, Mapping) else None
    return ConversationReference(
        conversation_id=(
            str(conversation.get("id") or "") if isinstance(conversation, Mapping) else ""
        ),
        service_url=str(activity.get("serviceUrl") or ""),
        tenant_id=str(tenant.get("id") or "") if isinstance(tenant, Mapping) else "",
        activity_id=str(activity.get("id") or ""),
    )


def target_of(activity: Mapping[str, Any]) -> ChatTarget:
    """Return the conversation ``activity`` happened in, thread and all.

    A personal chat has no thread of its own, so the conversation *is* the
    thread. Leaving it empty would make every direct message look like an
    unbound channel and stop mid-run context working in a one-to-one chat.
    """
    reference = reference_of(activity)
    conversation = activity.get("conversation")
    kind = (
        str(conversation.get("conversationType") or "") if isinstance(conversation, Mapping) else ""
    )
    thread = reference.thread_id or (
        reference.conversation_id if kind == CONVERSATION_PERSONAL else ""
    )
    return ChatTarget(
        platform=CHAT_PLATFORM_MICROSOFT_TEAMS,
        channel_id=reference.channel_id,
        thread_id=thread,
        workspace_id=reference.tenant_id,
    )


def user_of(activity: Mapping[str, Any]) -> PlatformUser | None:
    """Return who sent ``activity``, or ``None`` if it names nobody."""
    sender = activity.get("from")
    if not isinstance(sender, Mapping):
        return None
    user_id = str(sender.get("id") or "")
    if not user_id:
        return None
    channel_data = activity.get("channelData")
    tenant = channel_data.get("tenant") if isinstance(channel_data, Mapping) else None
    return PlatformUser(
        platform=CHAT_PLATFORM_MICROSOFT_TEAMS,
        user_id=user_id,
        display_name=str(sender.get("name") or ""),
        workspace_id=str(tenant.get("id") or "") if isinstance(tenant, Mapping) else "",
        email=str(sender.get("aadObjectId") or ""),
    )


def mentions(activity: Mapping[str, Any], bot_id: str) -> bool:
    """Return whether ``activity`` addressed this bot.

    A personal chat is addressed by definition: there is nobody else in it, and
    requiring a mention in a one-to-one conversation would mean the bot ignored
    everything said directly to it.
    """
    conversation = activity.get("conversation")
    if (
        isinstance(conversation, Mapping)
        and str(conversation.get("conversationType") or "") == CONVERSATION_PERSONAL
    ):
        return True
    entities = activity.get("entities")
    if not isinstance(entities, list):
        return False
    for entity in entities:
        if not isinstance(entity, Mapping) or entity.get("type") != "mention":
            continue
        mentioned = entity.get("mentioned")
        if isinstance(mentioned, Mapping) and str(mentioned.get("id") or "") == bot_id:
            return True
    return False


def strip_mentions(text: str) -> str:
    """Return ``text`` with Teams' ``<at>…</at>`` mention markup removed."""
    cleaned = text
    while "<at>" in cleaned and "</at>" in cleaned:
        head, _, rest = cleaned.partition("<at>")
        _, _, tail = rest.partition("</at>")
        cleaned = f"{head}{tail}"
    return cleaned.strip()


def parse_message(activity: Mapping[str, Any], *, bot_id: str) -> InboundMessage | None:
    """Return what ``activity`` says, or ``None`` if it says nothing to this bot."""
    if str(activity.get("type") or "") != MESSAGE_ACTIVITY:
        return None
    user = user_of(activity)
    if user is None:
        return None

    text = strip_mentions(str(activity.get("text") or ""))
    command, arguments = parse(text)
    return InboundMessage(
        target=target_of(activity),
        user=user,
        text=text,
        addressed=mentions(activity, bot_id),
        command=command,
        arguments=arguments,
        message_id=str(activity.get("id") or ""),
    )


def parse_decision(activity: Mapping[str, Any]) -> InteractionDecision | None:
    """Return the decision an Adaptive Card submission carries, or ``None``."""
    if str(activity.get("type") or "") != INVOKE_ACTIVITY:
        return None
    if str(activity.get("name") or "") != CARD_ACTION:
        return None
    data = _action_data(activity.get("value"))
    interaction_id = str(data.get("interaction_id") or "")
    if not interaction_id:
        return None
    user = user_of(activity)
    if user is None:
        return None
    return InteractionDecision(
        interaction_id=interaction_id,
        user=user,
        choice=str(data.get("choice") or ""),
        target=target_of(activity),
        element_id=str(activity.get("replyToId") or ""),
        text=str(data.get("text") or data.get("choice") or ""),
    )


def _action_data(value: Any) -> Mapping[str, Any]:
    """Return the payload an ``Action.Execute`` submission carried.

    Teams wraps it one level deeper than ``Action.Submit`` does, and both shapes
    reach the same endpoint, so both are read.
    """
    if not isinstance(value, Mapping):
        return {}
    action = value.get("action")
    if isinstance(action, Mapping):
        data = action.get("data")
        if isinstance(data, Mapping):
            return data
    data = value.get("data")
    return data if isinstance(data, Mapping) else value


__all__ = [
    "CARD_ACTION",
    "CONVERSATION_PERSONAL",
    "INVOKE_ACTIVITY",
    "MESSAGE_ACTIVITY",
    "THREAD_SEPARATOR",
    "ConversationReference",
    "mentions",
    "parse_decision",
    "parse_message",
    "reference_of",
    "strip_mentions",
    "target_of",
    "user_of",
]
