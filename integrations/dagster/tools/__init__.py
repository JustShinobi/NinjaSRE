"""Dagster's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
Dagster has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.dagster.tools.pipeline_health import dagster_pipeline_health
from integrations.dagster.tools.recent_failures import dagster_recent_failures

__all__ = [
    "dagster_pipeline_health",
    "dagster_recent_failures",
]
