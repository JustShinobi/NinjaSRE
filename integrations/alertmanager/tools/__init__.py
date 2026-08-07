"""Alertmanager's agent-callable capabilities.

3, and the set is the methodology rather than the API surface.
Alertmanager has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.alertmanager.tools.acknowledge_incident import alertmanager_acknowledge_incident
from integrations.alertmanager.tools.incident_statistics import alertmanager_incident_statistics
from integrations.alertmanager.tools.incident_timeline import alertmanager_incident_timeline

__all__ = [
    "alertmanager_acknowledge_incident",
    "alertmanager_incident_statistics",
    "alertmanager_incident_timeline",
]
