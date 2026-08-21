"""Rocket.Chat's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
Rocket.Chat has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.rocket_chat.tools.post_message import rocket_chat_post_message
from integrations.rocket_chat.tools.recent_messages import rocket_chat_recent_messages

__all__ = [
    "rocket_chat_post_message",
    "rocket_chat_recent_messages",
]
