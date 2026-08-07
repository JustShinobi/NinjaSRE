"""Snowflake's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
Snowflake has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.snowflake.tools.session_statistics import snowflake_session_statistics
from integrations.snowflake.tools.slow_queries import snowflake_slow_queries

__all__ = [
    "snowflake_session_statistics",
    "snowflake_slow_queries",
]
