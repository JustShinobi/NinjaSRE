"""Chat: the notification that lands where the incident is already being discussed.

This sink writes one line into a channel and nothing else. Rendering the report,
splitting it, attaching it, and holding the interactive controls are the chat
surface's job, and duplicating any of that here would be a second renderer that
drifts from the first.

**The adapter arrives as a port.** This is tier 3 and the four chat adapters are
an entry point, so a deployment hands over whatever it wired and nothing here
knows which platform it reached. That is the same seam every other outbound call
in this package uses, for the same reason: the whole suite runs with no socket.
"""

from __future__ import annotations

from dataclasses import dataclass

from platform.notifications.models import (
    ChatNotifier,
    Notification,
    NotificationSink,
    SinkKind,
)


@dataclass(slots=True)
class ChatSink:
    """Posts one notification line into a channel."""

    notifier: ChatNotifier

    @property
    def kind(self) -> SinkKind:
        """Return the sink kind this delivers to."""
        return SinkKind.CHAT

    def line_for(self, notification: Notification) -> str:
        """Return the single line this notification becomes in a channel.

        Severity first, because a channel is read by scanning down the left edge,
        and the link last, because that is where a reader's eye stops when they
        have decided to act.
        """
        parts = [f"[{notification.severity.value}] {notification.title}"]
        if notification.message:
            parts.append(notification.message)
        if notification.link:
            parts.append(notification.link)
        return " — ".join(parts)

    async def deliver(self, notification: Notification, sink: NotificationSink) -> None:
        """Post ``notification`` to ``sink``'s channel."""
        await self.notifier.notify(sink.target, self.line_for(notification))


__all__ = ["ChatSink"]
