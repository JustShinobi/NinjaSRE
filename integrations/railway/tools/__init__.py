"""Railway's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
Railway has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.railway.tools.failed_runs import railway_failed_runs
from integrations.railway.tools.pipeline_statistics import railway_pipeline_statistics

__all__ = [
    "railway_failed_runs",
    "railway_pipeline_statistics",
]
