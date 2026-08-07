"""PagerDuty: the sink for the outcomes a team has already decided are pages.

Uses the Events API's three actions rather than only ``trigger``, because a
notification system that can only open incidents is one whose incidents are
closed by hand — and an incident nobody closed is why the next real page is
ignored.

**The dedup key is the notification's fingerprint.** PagerDuty collapses
triggers that share one, so a repeat inside its own cooldown reaches the same
incident rather than opening a second. That is the same property the local
cooldown provides, asserted a second time at the vendor: the two are independent
and both can be the one that is misconfigured.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from platform.notifications.models import (
    Notification,
    NotificationSink,
    NotificationTransport,
    Outcome,
    Severity,
    SinkCall,
    SinkKind,
)

#: The Events API v2 enqueue path.
PAGERDUTY_EVENT_PATH = "/v2/enqueue"

#: What PagerDuty calls each of our severities. Its scale is four wide and ours
#: is five, so ``noise`` and ``low`` share the bottom — a distinction that
#: matters for whether we notify at all, and not for how PagerDuty files it.
PAGERDUTY_SEVERITIES: dict[Severity, str] = {
    Severity.CRITICAL: "critical",
    Severity.HIGH: "error",
    Severity.MEDIUM: "warning",
    Severity.LOW: "info",
    Severity.NOISE: "info",
}


@dataclass(slots=True)
class PagerDutySink:
    """Triggers or resolves a PagerDuty incident for one notification."""

    transport: NotificationTransport
    source: str = "ninjasre"

    @property
    def kind(self) -> SinkKind:
        """Return the sink kind this delivers to."""
        return SinkKind.PAGERDUTY

    def call_for(self, notification: Notification, sink: NotificationSink) -> SinkCall:
        """Return the event ``notification`` becomes."""
        action = "resolve" if notification.outcome is Outcome.RESOLVED else "trigger"
        payload: dict[str, Any] = {
            "routing_key": sink.target,
            "event_action": action,
            "dedup_key": notification.fingerprint,
        }
        if action == "trigger":
            payload["payload"] = {
                "summary": notification.title,
                "severity": PAGERDUTY_SEVERITIES[notification.severity],
                "source": self.source,
                "custom_details": {
                    "message": notification.message,
                    "run_id": notification.run_id,
                    "team_node_id": notification.team_node_id,
                },
            }
            if notification.link:
                payload["links"] = [{"href": notification.link, "text": "Open the investigation"}]
        return SinkCall(method="POST", path=PAGERDUTY_EVENT_PATH, payload=payload)

    async def deliver(self, notification: Notification, sink: NotificationSink) -> None:
        """Send ``notification`` to ``sink``."""
        await self.transport.send(self.call_for(notification, sink))


__all__ = ["PAGERDUTY_EVENT_PATH", "PAGERDUTY_SEVERITIES", "PagerDutySink"]
