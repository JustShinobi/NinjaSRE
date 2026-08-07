"""Getting somebody's attention once, at the right severity, without waking anyone else.

The report is the thing a human reads; this package is what gets them to it. Its
whole surface area is about *not* notifying: severity routing, quiet hours,
cooldown, per-team rate limits, and an escalation that cancels when the thing it
was escalating resolves. Every one of those decisions is recorded, because "why
wasn't I told?" is the question asked after every missed incident and silence is
not an answer to it.
"""

from __future__ import annotations

from platform.notifications.configuration import destinations_of, policy_of, sinks_of
from platform.notifications.cooldown import Cooldown, Suppression
from platform.notifications.escalation import (
    Escalation,
    EscalationRegistry,
    EscalationState,
)
from platform.notifications.limits import RateLimitDecision, RateLimiter
from platform.notifications.models import (
    ChatNotifier,
    Notification,
    NotificationDecision,
    NotificationError,
    NotificationRecord,
    NotificationSink,
    NotificationTransport,
    NotificationUnavailable,
    Outcome,
    Severity,
    SinkCall,
    SinkKind,
)
from platform.notifications.policy import NotificationPolicy, QuietHours, Routing
from platform.notifications.redaction import SinkRedactor
from platform.notifications.service import (
    NotificationService,
    NotificationTrace,
    SinkDelivery,
    deliveries_of,
    escalation_severity,
)
from platform.notifications.sinks import (
    ChatSink,
    EmailSink,
    PagerDutySink,
    PushoverSink,
    WebhookSink,
)
from platform.notifications.trace import RunTraceNotificationLog

__all__ = [
    "ChatNotifier",
    "ChatSink",
    "Cooldown",
    "EmailSink",
    "Escalation",
    "EscalationRegistry",
    "EscalationState",
    "Notification",
    "NotificationDecision",
    "NotificationError",
    "NotificationPolicy",
    "NotificationRecord",
    "NotificationService",
    "NotificationSink",
    "NotificationTrace",
    "NotificationTransport",
    "NotificationUnavailable",
    "Outcome",
    "PagerDutySink",
    "PushoverSink",
    "QuietHours",
    "RateLimitDecision",
    "RateLimiter",
    "Routing",
    "RunTraceNotificationLog",
    "Severity",
    "SinkCall",
    "SinkDelivery",
    "SinkKind",
    "SinkRedactor",
    "Suppression",
    "WebhookSink",
    "deliveries_of",
    "destinations_of",
    "escalation_severity",
    "policy_of",
    "sinks_of",
]
