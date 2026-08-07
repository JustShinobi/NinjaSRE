"""One chat abstraction, four thin adapters.

A behaviour is implemented here and rendered per platform. What lives in an
adapter is translation — Block Kit, an Adaptive Card, an inline keyboard, a
message component — and nothing that decides anything.
"""

from __future__ import annotations

from gateway.chat.port import (
    Attachment,
    ChatError,
    ChatPlatform,
    ChatRateLimited,
    ChatTarget,
    ChatTransport,
    ChatUnavailable,
    InboundMessage,
    InteractionDecision,
    InteractiveElement,
    PlatformCall,
    PlatformLimits,
    PlatformReply,
    PlatformUser,
    PostedMessage,
    ThreadMessage,
)

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
