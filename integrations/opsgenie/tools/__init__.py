"""Opsgenie's agent-callable capabilities.

3, and the set is the methodology rather than the API surface.
Opsgenie has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.opsgenie.tools.acknowledge_incident import opsgenie_acknowledge_incident
from integrations.opsgenie.tools.incident_statistics import opsgenie_incident_statistics
from integrations.opsgenie.tools.incident_timeline import opsgenie_incident_timeline

__all__ = [
    "opsgenie_acknowledge_incident",
    "opsgenie_incident_statistics",
    "opsgenie_incident_timeline",
]
