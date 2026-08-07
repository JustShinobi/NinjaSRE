"""Telegram's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
Telegram has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.telegram.tools.post_message import telegram_post_message
from integrations.telegram.tools.recent_messages import telegram_recent_messages

__all__ = [
    "telegram_post_message",
    "telegram_recent_messages",
]
