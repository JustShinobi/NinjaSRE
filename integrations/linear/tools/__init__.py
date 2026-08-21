"""Linear's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
Linear has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.linear.tools.issue_statistics import linear_issue_statistics
from integrations.linear.tools.recent_issues import linear_recent_issues

__all__ = [
    "linear_issue_statistics",
    "linear_recent_issues",
]
