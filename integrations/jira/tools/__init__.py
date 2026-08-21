"""Jira's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
Jira has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.jira.tools.issue_statistics import jira_issue_statistics
from integrations.jira.tools.recent_issues import jira_recent_issues

__all__ = [
    "jira_issue_statistics",
    "jira_recent_issues",
]
