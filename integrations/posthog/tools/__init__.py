"""PostHog's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
PostHog has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.posthog.tools.active_alerts import posthog_active_alerts
from integrations.posthog.tools.metric_statistics import posthog_metric_statistics

__all__ = [
    "posthog_active_alerts",
    "posthog_metric_statistics",
]
