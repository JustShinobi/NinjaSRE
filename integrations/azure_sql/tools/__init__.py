"""Azure SQL's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
Azure SQL has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.azure_sql.tools.session_statistics import azure_sql_session_statistics
from integrations.azure_sql.tools.slow_queries import azure_sql_slow_queries

__all__ = [
    "azure_sql_session_statistics",
    "azure_sql_slow_queries",
]
