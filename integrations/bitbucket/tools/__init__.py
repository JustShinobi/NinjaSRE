"""Bitbucket's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
Bitbucket has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.bitbucket.tools.change_statistics import bitbucket_change_statistics
from integrations.bitbucket.tools.recent_changes import bitbucket_recent_changes

__all__ = [
    "bitbucket_change_statistics",
    "bitbucket_recent_changes",
]
