"""GitLab's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
GitLab has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.gitlab.tools.change_statistics import gitlab_change_statistics
from integrations.gitlab.tools.recent_changes import gitlab_recent_changes

__all__ = [
    "gitlab_change_statistics",
    "gitlab_recent_changes",
]
