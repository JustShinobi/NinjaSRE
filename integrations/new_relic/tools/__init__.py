"""New Relic's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
New Relic has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.new_relic.tools.active_alerts import new_relic_active_alerts
from integrations.new_relic.tools.metric_statistics import new_relic_metric_statistics

__all__ = [
    "new_relic_active_alerts",
    "new_relic_metric_statistics",
]
