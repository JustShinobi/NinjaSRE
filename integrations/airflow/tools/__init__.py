"""Airflow's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
Airflow has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.airflow.tools.pipeline_health import airflow_pipeline_health
from integrations.airflow.tools.recent_failures import airflow_recent_failures

__all__ = [
    "airflow_pipeline_health",
    "airflow_recent_failures",
]
