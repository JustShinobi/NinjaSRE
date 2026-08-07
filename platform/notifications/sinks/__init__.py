"""One module per notification target, each building a call and sending nothing else.

Every sink here has the same two-method shape — ``kind`` and ``deliver`` — plus a
``call_for`` or ``line_for`` that builds what would be sent without sending it.
That second method is what lets an operator's dry run and the whole test suite
see exactly what a device would be told, with no network in the way.
"""

from __future__ import annotations

from platform.notifications.sinks.chat import ChatSink
from platform.notifications.sinks.email import EmailSink
from platform.notifications.sinks.pagerduty import PagerDutySink
from platform.notifications.sinks.pushover import PushoverSink
from platform.notifications.sinks.webhook import WebhookSink

__all__ = [
    "ChatSink",
    "EmailSink",
    "PagerDutySink",
    "PushoverSink",
    "WebhookSink",
]
