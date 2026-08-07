"""Pushover's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
Pushover has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.pushover.tools.post_message import pushover_post_message
from integrations.pushover.tools.recent_messages import pushover_recent_messages

__all__ = [
    "pushover_post_message",
    "pushover_recent_messages",
]
