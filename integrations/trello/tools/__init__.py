"""Trello's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
Trello has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.trello.tools.issue_statistics import trello_issue_statistics
from integrations.trello.tools.recent_issues import trello_recent_issues

__all__ = [
    "trello_issue_statistics",
    "trello_recent_issues",
]
