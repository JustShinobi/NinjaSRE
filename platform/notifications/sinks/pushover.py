"""Pushover: the shortest path from a conclusion to a phone.

Worth having as its own sink because of what it does *not* depend on. A team
without Slack has nowhere for a chat notification to go; and an escalation about
an incident in the chat platform itself must not travel through the chat
platform. Pushover needs neither, which makes it the sink that still works on the
night the others do not.

Three things the vendor decides and this module has to respect.

**Priority is a scale with meaning, not a number.** ``emergency`` repeats until
somebody acknowledges it, so nothing below a critical outcome may reach it — a
platform that emergency-pages for a medium finding trains its users to turn
Pushover off, and then it is not there on the night it is needed.

**Title and message have hard maxima.** The API refuses a longer one, so an
oversized notification is *summarised to fit here* rather than refused at 03:00.
The link survives the summarising, which is what keeps a shortened message useful.

**The link is a first-class field.** ``url`` and ``url_title`` render as a button,
so the recipient goes from the lock screen to the run without typing anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config.constants.notifications import (
    PUSHOVER_MAX_MESSAGE_CHARS,
    PUSHOVER_MAX_TITLE_CHARS,
    PUSHOVER_MAX_URL_CHARS,
    PUSHOVER_PRIORITY_EMERGENCY,
    PUSHOVER_PRIORITY_HIGH,
    PUSHOVER_PRIORITY_LOW,
    PUSHOVER_PRIORITY_LOWEST,
    PUSHOVER_PRIORITY_NORMAL,
    PUSHOVER_SOUND_DEFAULT,
    PUSHOVER_SOUND_PAGING,
)
from platform.notifications.models import (
    Notification,
    NotificationSink,
    NotificationTransport,
    Severity,
    SinkCall,
    SinkKind,
)

#: The vendor's message endpoint. A path rather than a URL: the transport owns
#: the host, so a self-hosted or proxied deployment changes one place.
PUSHOVER_MESSAGE_PATH = "/1/messages.json"

#: What "how urgent is this" means on Pushover's own scale.
PUSHOVER_PRIORITIES: dict[Severity, int] = {
    Severity.CRITICAL: PUSHOVER_PRIORITY_EMERGENCY,
    Severity.HIGH: PUSHOVER_PRIORITY_HIGH,
    Severity.MEDIUM: PUSHOVER_PRIORITY_NORMAL,
    Severity.LOW: PUSHOVER_PRIORITY_LOW,
    Severity.NOISE: PUSHOVER_PRIORITY_LOWEST,
}

#: The label on the button the notification carries.
RUN_LINK_TITLE = "Open the investigation"

#: What a shortened message ends with, so a reader can tell it was shortened.
ELLIPSIS = "…"


@dataclass(slots=True)
class PushoverSink:
    """Sends one notification to a Pushover device or group."""

    transport: NotificationTransport

    @property
    def kind(self) -> SinkKind:
        """Return the sink kind this delivers to."""
        return SinkKind.PUSHOVER

    def call_for(self, notification: Notification, sink: NotificationSink) -> SinkCall:
        """Return the API call ``notification`` becomes.

        Built separately from sending so a test — and an operator's dry run — can
        see exactly what the device would be told without a network in the way.
        """
        payload: dict[str, Any] = {
            "user": sink.target,
            "title": _fit(notification.title, PUSHOVER_MAX_TITLE_CHARS),
            "message": _fit(notification.message or notification.title, PUSHOVER_MAX_MESSAGE_CHARS),
            "priority": PUSHOVER_PRIORITIES[notification.severity],
            "sound": _sound(notification.severity, sink),
        }
        if notification.link:
            payload["url"] = notification.link[:PUSHOVER_MAX_URL_CHARS]
            payload["url_title"] = RUN_LINK_TITLE
        device = sink.options.get("device")
        if device:
            payload["device"] = device
        return SinkCall(method="POST", path=PUSHOVER_MESSAGE_PATH, payload=payload)

    async def deliver(self, notification: Notification, sink: NotificationSink) -> None:
        """Send ``notification`` to ``sink``."""
        await self.transport.send(self.call_for(notification, sink))


def _sound(severity: Severity, sink: NotificationSink) -> str:
    """Return the sound this notification arrives with.

    A team's own choice wins. The default is loud only for the severities that
    are meant to wake somebody — the sound is the part the recipient hears before
    they have read anything, and a loud one for a low-severity finding is how a
    notification channel gets muted.
    """
    configured = sink.options.get("sound")
    if configured:
        return configured
    return PUSHOVER_SOUND_PAGING if severity.pages else PUSHOVER_SOUND_DEFAULT


def _fit(text: str, limit: int) -> str:
    """Return ``text`` within ``limit``, marked when it had to be shortened.

    The vendor refuses a longer value outright, so this is the one place in the
    feature where content is cut rather than summarised — and it is marked, so
    nothing reads as complete when it is not. The full text is always a tap away
    behind the link.
    """
    if len(text) <= limit:
        return text
    return text[: limit - len(ELLIPSIS)] + ELLIPSIS


__all__ = [
    "ELLIPSIS",
    "PUSHOVER_MESSAGE_PATH",
    "PUSHOVER_PRIORITIES",
    "RUN_LINK_TITLE",
    "PushoverSink",
]
