"""Temporal's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
Temporal has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.temporal.tools.pipeline_health import temporal_pipeline_health
from integrations.temporal.tools.recent_failures import temporal_recent_failures

__all__ = [
    "temporal_pipeline_health",
    "temporal_recent_failures",
]
