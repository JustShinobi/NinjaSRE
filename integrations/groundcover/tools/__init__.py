"""groundcover's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
groundcover has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.groundcover.tools.active_alerts import groundcover_active_alerts
from integrations.groundcover.tools.metric_statistics import groundcover_metric_statistics

__all__ = [
    "groundcover_active_alerts",
    "groundcover_metric_statistics",
]
