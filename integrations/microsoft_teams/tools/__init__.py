"""Microsoft Teams's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
Microsoft Teams has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.microsoft_teams.tools.post_message import microsoft_teams_post_message
from integrations.microsoft_teams.tools.recent_messages import microsoft_teams_recent_messages

__all__ = [
    "microsoft_teams_post_message",
    "microsoft_teams_recent_messages",
]
