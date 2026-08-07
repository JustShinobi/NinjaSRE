"""Discord's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
Discord has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.discord.tools.post_message import discord_post_message
from integrations.discord.tools.recent_messages import discord_recent_messages

__all__ = [
    "discord_post_message",
    "discord_recent_messages",
]
