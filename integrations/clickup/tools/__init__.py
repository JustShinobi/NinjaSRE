"""ClickUp's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
ClickUp has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.clickup.tools.issue_statistics import clickup_issue_statistics
from integrations.clickup.tools.recent_issues import clickup_recent_issues

__all__ = [
    "clickup_issue_statistics",
    "clickup_recent_issues",
]
