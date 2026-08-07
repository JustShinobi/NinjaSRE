"""OpenSearch's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
OpenSearch has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.opensearch.tools.log_statistics import opensearch_log_statistics
from integrations.opensearch.tools.sample_logs import opensearch_sample_logs

__all__ = [
    "opensearch_log_statistics",
    "opensearch_sample_logs",
]
