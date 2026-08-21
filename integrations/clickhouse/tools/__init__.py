"""ClickHouse's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
ClickHouse has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.clickhouse.tools.session_statistics import clickhouse_session_statistics
from integrations.clickhouse.tools.slow_queries import clickhouse_slow_queries

__all__ = [
    "clickhouse_session_statistics",
    "clickhouse_slow_queries",
]
