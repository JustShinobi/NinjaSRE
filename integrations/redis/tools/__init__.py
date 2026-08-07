"""Redis Cloud's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
Redis Cloud has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.redis.tools.session_statistics import redis_session_statistics
from integrations.redis.tools.slow_queries import redis_slow_queries

__all__ = [
    "redis_session_statistics",
    "redis_slow_queries",
]
