"""A webhook: the operator's own automation, told in a shape it can parse.

The one sink whose payload is structured rather than prose. Everything else here
produces something a person reads; this produces something a script reads, so it
carries the fields — subject, severity, outcome, team, run, link — rather than a
sentence containing them.

The payload is a fixed shape with a version on it. An operator's receiver is code
somebody wrote once and will not revisit, so a field appearing or changing meaning
without the version moving is a receiver that silently misreads every event after
the release.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from platform.notifications.models import (
    Notification,
    NotificationSink,
    NotificationTransport,
    SinkCall,
    SinkKind,
)

#: Bumped when a field appears, disappears, or changes meaning. Carried in every
#: payload so a receiver can refuse a version it does not understand rather than
#: misreading it.
WEBHOOK_PAYLOAD_VERSION = "v1"


@dataclass(slots=True)
class WebhookSink:
    """Posts one notification to an operator-configured endpoint."""

    transport: NotificationTransport

    @property
    def kind(self) -> SinkKind:
        """Return the sink kind this delivers to."""
        return SinkKind.WEBHOOK

    def call_for(self, notification: Notification, sink: NotificationSink) -> SinkCall:
        """Return the request ``notification`` becomes."""
        payload: dict[str, Any] = {
            "version": WEBHOOK_PAYLOAD_VERSION,
            "subject": notification.subject,
            "title": notification.title,
            "message": notification.message,
            "severity": notification.severity.value,
            "outcome": notification.outcome.value,
            "team_node_id": notification.team_node_id,
            "run_id": notification.run_id,
            "link": notification.link,
        }
        return SinkCall(method="POST", path=sink.target, payload=payload)

    async def deliver(self, notification: Notification, sink: NotificationSink) -> None:
        """Send ``notification`` to ``sink``."""
        await self.transport.send(self.call_for(notification, sink))


__all__ = ["WEBHOOK_PAYLOAD_VERSION", "WebhookSink"]
