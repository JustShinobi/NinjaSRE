"""Email: the sink for what somebody reads in the morning rather than at 03:14.

Deliberately not a paging route. An email that is meant to wake somebody is an
email nobody is watching for, and treating it as urgent makes both this sink and
the paging ones less trusted. It carries the notifications a team wants a record
of — a resolved outcome, a low-severity finding, the digest of what was
suppressed.

Two parts are produced, always: a plain-text body and an HTML one. A missing
plain part means a terminal mail reader, a corporate policy, or a screen reader
gets markup instead of a message.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any

from platform.notifications.models import (
    Notification,
    NotificationSink,
    NotificationTransport,
    SinkCall,
    SinkKind,
)

#: The submission path an email transport exposes. The transport owns whether
#: that is SMTP, a vendor API, or a local queue.
EMAIL_SEND_PATH = "/send"


@dataclass(slots=True)
class EmailSink:
    """Sends one notification as an email with both alternatives."""

    transport: NotificationTransport
    sender: str = ""

    @property
    def kind(self) -> SinkKind:
        """Return the sink kind this delivers to."""
        return SinkKind.EMAIL

    def call_for(self, notification: Notification, sink: NotificationSink) -> SinkCall:
        """Return the submission ``notification`` becomes."""
        link_line = f"\n\n{notification.link}" if notification.link else ""
        payload: dict[str, Any] = {
            "to": sink.target,
            "from": self.sender or sink.options.get("from", ""),
            "subject": notification.title,
            "text": f"{notification.message}{link_line}".strip(),
            "html": _html(notification),
        }
        return SinkCall(method="POST", path=EMAIL_SEND_PATH, payload=payload)

    async def deliver(self, notification: Notification, sink: NotificationSink) -> None:
        """Send ``notification`` to ``sink``."""
        await self.transport.send(self.call_for(notification, sink))


def _html(notification: Notification) -> str:
    """Return the HTML alternative, with every value escaped.

    The content comes from a model's output and from other systems' logs, and it
    is delivered to a client that renders markup. Escaping is a security property
    here rather than a rendering nicety.
    """
    body = f"<h1>{escape(notification.title)}</h1><p>{escape(notification.message)}</p>"
    if notification.link:
        link = escape(notification.link, quote=True)
        body += f'<p><a href="{link}">Open the investigation</a></p>'
    return body


__all__ = ["EMAIL_SEND_PATH", "EmailSink"]
