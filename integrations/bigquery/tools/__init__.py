"""BigQuery's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
BigQuery has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.bigquery.tools.session_statistics import bigquery_session_statistics
from integrations.bigquery.tools.slow_queries import bigquery_slow_queries

__all__ = [
    "bigquery_session_statistics",
    "bigquery_slow_queries",
]
