"""What a chat platform has to be, and the vocabulary the four speak.

One protocol and the value types it moves. Everything a behaviour needs — where
a message goes, which message to rewrite, who typed it, what a button press
decided — is named here so that implementing a behaviour means implementing it
in ``gateway/chat/`` and wiring four thin adapters, rather than writing it four
times.

**An adapter translates; it never decides.** Rendering an approval as Block Kit,
an Adaptive Card, an inline keyboard, or a message component is per-platform.
*What* an approval shows, when the progress message is rewritten, what an
unmapped user is told, and whether a report is split or attached are not, and
none of them live in an adapter.

**The transport is a seam, not a dependency.** A platform's methods are
``async`` and raise ``ChatRateLimited`` or ``ChatUnavailable``; nothing here
knows about sockets, and the concrete authenticated client for each platform is
built by whoever wires the deployment. That is what lets the shared contract
suite drive all four adapters with no network — and it is the same seam
``gateway/http/services.py`` puts in front of a runtime, for the same reason.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from config.constants.surfaces import (
    CHAT_MAX_EDITS_PER_MINUTE,
    CHAT_MESSAGE_LIMITS,
    CHAT_PLATFORMS,
)
from core.agent.interaction.closure import InteractionEvent
from core.agent.interaction.models import Interaction


class ChatError(Exception):
    """Base for everything a chat transport raises."""


class ChatRateLimited(ChatError):
    """The platform refused this call and said when to try again.

    ``retry_after_seconds`` is the platform's own number when it sent one. It
    always wins over the configured backoff: a vendor that says four seconds
    knows something the caller's doubling does not.
    """

    def __init__(self, platform: str, *, retry_after_seconds: float = 0.0) -> None:
        self.platform = platform
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"{platform} rate-limited this call")


class ChatUnavailable(ChatError):
    """The platform could not be reached, or answered that it cannot do this now.

    Covers the outage, the dropped socket, and the bot being removed from the
    channel it was posting into. All three mean the same thing to a caller: this
    surface is not available, and the run continues without it.
    """

    def __init__(self, platform: str, reason: str = "") -> None:
        self.platform = platform
        self.reason = reason
        super().__init__(f"{platform} is not available{f': {reason}' if reason else ''}")


@dataclass(frozen=True, slots=True)
class PlatformCall:
    """One request to a platform's API, built by an adapter and carrying no credential.

    All four platforms are HTTP JSON APIs, so one call shape covers them and the
    per-platform part is the path and the payload — which is exactly the part
    that belongs to an adapter. A transport that had to know which platform it
    was carrying for would be a fifth place the four differ.
    """

    method: str
    path: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    query: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PlatformReply:
    """What a platform answered, before an adapter decides what it means."""

    status: int
    document: Mapping[str, Any] = field(default_factory=dict)
    #: The platform's own ``Retry-After``, in seconds, when it sent one.
    retry_after_seconds: float = 0.0

    @property
    def ok(self) -> bool:
        """Return whether the platform accepted the call."""
        return 200 <= self.status < 300


@runtime_checkable
class ChatTransport(Protocol):
    """Carries one platform call and brings the answer back.

    A protocol for the reason ``integrations/_base/transport.py`` states one:
    the credential belongs at the network edge, not in the caller, and a seam
    here is what lets the whole contract suite run with no socket and no token.
    """

    async def send(self, call: PlatformCall) -> PlatformReply:
        """Return the platform's answer to ``call``.

        Raises ``ChatRateLimited`` when the platform refused for rate, and
        ``ChatUnavailable`` when nothing came back at all.
        """


@dataclass(frozen=True, slots=True)
class PlatformLimits:
    """The bounds a platform imposes, read from configuration rather than guessed."""

    platform: str
    message_limit: int
    edits_per_minute: int
    supports_attachments: bool = True

    @classmethod
    def of(cls, platform: str, *, supports_attachments: bool = True) -> PlatformLimits:
        """Return the configured limits for ``platform``.

        Raises:
            ValueError: ``platform`` is not one of the four.
        """
        if platform not in CHAT_PLATFORMS:
            raise ValueError(
                f"{platform!r} is not a chat platform. Known: {', '.join(CHAT_PLATFORMS)}."
            )
        return cls(
            platform=platform,
            message_limit=CHAT_MESSAGE_LIMITS[platform],
            edits_per_minute=CHAT_MAX_EDITS_PER_MINUTE[platform],
            supports_attachments=supports_attachments,
        )


@dataclass(frozen=True, slots=True)
class ChatTarget:
    """Where a message goes: a channel, and the thread inside it.

    ``thread_id`` empty means the channel itself. An investigation always runs
    in a thread, so a sink that finds this empty is one that has not
    been bound yet rather than one that may post to the channel.
    """

    platform: str
    channel_id: str
    thread_id: str = ""
    #: The workspace, guild, team, or tenant the channel belongs to. Part of
    #: routing and of identity: two workspaces may both have a ``U1``.
    workspace_id: str = ""

    def in_thread(self, thread_id: str) -> ChatTarget:
        """Return this target bound to ``thread_id``."""
        return ChatTarget(
            platform=self.platform,
            channel_id=self.channel_id,
            thread_id=thread_id,
            workspace_id=self.workspace_id,
        )

    @property
    def is_threaded(self) -> bool:
        """Return whether this target names a thread rather than a whole channel."""
        return bool(self.thread_id)

    @property
    def key(self) -> str:
        """Return the identifier a routing or binding table keys on."""
        return f"{self.platform}:{self.workspace_id}:{self.channel_id}:{self.thread_id}"


@dataclass(frozen=True, slots=True)
class PostedMessage:
    """A message that exists on a platform, and can therefore be rewritten.

    ``message_id`` is whatever the platform calls it — a Slack ``ts``, a Teams
    activity id, a Telegram ``message_id``, a Discord snowflake. Nothing above
    an adapter parses it.
    """

    target: ChatTarget
    message_id: str
    text: str = ""

    def with_text(self, text: str) -> PostedMessage:
        """Return this message as it reads after an edit."""
        return PostedMessage(target=self.target, message_id=self.message_id, text=text)


@dataclass(frozen=True, slots=True)
class Attachment:
    """A report too long to post as messages, delivered as a file instead."""

    filename: str
    content: str
    title: str = ""


@dataclass(frozen=True, slots=True)
class PlatformUser:
    """Somebody on a platform, before anything is known about who they are here.

    Deliberately not a principal. Turning one into the other is
    ``gateway/chat/identity.py``'s job, it can fail, and a type that conflated
    the two would make the failure unrepresentable.
    """

    platform: str
    user_id: str
    display_name: str = ""
    workspace_id: str = ""
    email: str = ""

    @property
    def key(self) -> str:
        """Return the identifier an identity mapping is keyed on."""
        return f"{self.platform}:{self.workspace_id}:{self.user_id}"


@dataclass(frozen=True, slots=True)
class InboundMessage:
    """One thing somebody said that this bot is meant to read.

    An adapter produces this from a platform payload and nothing else produces
    it. ``addressed`` is what distinguishes "start an investigation" from "a
    message in a thread the bot is already following" — both are inbound, and
    only the first one starts a run.
    """

    target: ChatTarget
    user: PlatformUser
    text: str
    #: The bot was mentioned, or a command was issued at it.
    addressed: bool = False
    #: The command name, without its platform's prefix, when this is a command.
    command: str = ""
    arguments: str = ""
    #: The platform's identifier for this message, so a reply can quote it.
    message_id: str = ""

    @property
    def is_command(self) -> bool:
        """Return whether this message invoked a command rather than free text."""
        return bool(self.command)


@dataclass(frozen=True, slots=True)
class InteractionDecision:
    """A button press, a card submission, or a callback query.

    Carries the platform's own handle on the element (``element_id``) as well as
    the interaction it decides, because closing the element is what the adapter
    has to do after the core has recorded the decision.
    """

    interaction_id: str
    user: PlatformUser
    choice: str
    target: ChatTarget
    element_id: str = ""
    text: str = ""


@dataclass(frozen=True, slots=True)
class InteractiveElement:
    """The platform-native control an approval or a question renders to.

    ``payload`` is opaque above the adapter that built it: Block Kit blocks, an
    Adaptive Card, an inline keyboard, a component row. ``fallback_text`` is
    what a client that cannot render the control shows, and is never empty —
    a notification, an email digest, and an accessibility reader all read it.
    """

    interaction_id: str
    kind: str
    fallback_text: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    #: The choices this element offers, in the order it offers them. Read by the
    #: contract suite, which asserts an approval is decidable inline.
    choices: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ThreadMessage:
    """One earlier message of a thread, as history ingestion sees it.

    Not an ``InboundMessage``: history is *observed context*, never a request,
    and giving it the type that means "somebody asked for something" is how it
    would eventually be treated as one.
    """

    author: str
    text: str
    posted_at: str = ""
    is_bot: bool = False


@runtime_checkable
class ChatPlatform(Protocol):
    """One platform, seen as the four things every behaviour needs of it.

    Receive, stream, render an interaction, resolve an identity — the plan's
    four, in the shapes the shared modules call them with.
    """

    @property
    def name(self) -> str:
        """Return which of the four platforms this is."""

    @property
    def limits(self) -> PlatformLimits:
        """Return the message and edit-rate bounds this platform imposes."""

    # -- receive ---------------------------------------------------------------

    def parse_message(self, payload: Mapping[str, Any]) -> InboundMessage | None:
        """Return what ``payload`` says, or ``None`` if it says nothing to this bot."""

    def parse_decision(self, payload: Mapping[str, Any]) -> InteractionDecision | None:
        """Return the interaction decision ``payload`` carries, or ``None``."""

    async def thread_history(self, target: ChatTarget, *, limit: int) -> Sequence[ThreadMessage]:
        """Return up to ``limit`` earlier messages of ``target``'s thread, oldest first."""

    # -- stream ----------------------------------------------------------------

    async def post(self, target: ChatTarget, text: str) -> PostedMessage:
        """Post ``text`` to ``target`` and return the message that now exists."""

    async def edit(self, message: PostedMessage, text: str) -> PostedMessage:
        """Rewrite ``message`` to say ``text`` and return it as it now reads."""

    async def attach(self, target: ChatTarget, attachment: Attachment) -> PostedMessage:
        """Deliver ``attachment`` to ``target`` as a file."""

    # -- render an interaction -------------------------------------------------

    def render_interaction(self, interaction: Interaction) -> InteractiveElement:
        """Return the platform-native control ``interaction`` is decided with."""

    async def send_interaction(
        self, target: ChatTarget, element: InteractiveElement
    ) -> PostedMessage:
        """Show ``element`` in ``target`` and return the message carrying it."""

    async def close_interaction(self, message: PostedMessage, event: InteractionEvent) -> None:
        """Replace ``message``'s control with the outcome ``event`` records."""

    # -- resolve an identity ---------------------------------------------------

    def user_of(self, payload: Mapping[str, Any]) -> PlatformUser | None:
        """Return the platform user ``payload`` was produced by, or ``None``."""


__all__ = [
    "Attachment",
    "ChatError",
    "ChatPlatform",
    "ChatRateLimited",
    "ChatTarget",
    "ChatTransport",
    "ChatUnavailable",
    "InboundMessage",
    "InteractionDecision",
    "InteractiveElement",
    "PlatformCall",
    "PlatformLimits",
    "PlatformReply",
    "PlatformUser",
    "PostedMessage",
    "ThreadMessage",
]
