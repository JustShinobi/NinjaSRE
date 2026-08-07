"""WhatsApp's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
WhatsApp has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.whatsapp.tools.post_message import whatsapp_post_message
from integrations.whatsapp.tools.recent_messages import whatsapp_recent_messages

__all__ = [
    "whatsapp_post_message",
    "whatsapp_recent_messages",
]
