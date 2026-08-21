"""Slack's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
Slack has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.slack.tools.post_message import slack_post_message
from integrations.slack.tools.recent_messages import slack_recent_messages

__all__ = [
    "slack_post_message",
    "slack_recent_messages",
]
