"""Prometheus's agent-callable capabilities.

3, and the set is the methodology rather than the API surface.
Prometheus has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.prometheus.tools.active_alerts import prometheus_active_alerts
from integrations.prometheus.tools.metric_statistics import prometheus_metric_statistics
from integrations.prometheus.tools.resource_pressure import prometheus_resource_pressure

__all__ = [
    "prometheus_active_alerts",
    "prometheus_metric_statistics",
    "prometheus_resource_pressure",
]
