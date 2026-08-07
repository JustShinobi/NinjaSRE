"""MongoDB Atlas's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
MongoDB Atlas has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.mongodb_atlas.tools.session_statistics import mongodb_atlas_session_statistics
from integrations.mongodb_atlas.tools.slow_queries import mongodb_atlas_slow_queries

__all__ = [
    "mongodb_atlas_session_statistics",
    "mongodb_atlas_slow_queries",
]
