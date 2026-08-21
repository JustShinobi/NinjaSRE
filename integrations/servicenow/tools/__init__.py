"""ServiceNow's agent-callable capabilities.

3, and the set is the methodology rather than the API surface.
ServiceNow has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.servicenow.tools.acknowledge_incident import servicenow_acknowledge_incident
from integrations.servicenow.tools.incident_statistics import servicenow_incident_statistics
from integrations.servicenow.tools.incident_timeline import servicenow_incident_timeline

__all__ = [
    "servicenow_acknowledge_incident",
    "servicenow_incident_statistics",
    "servicenow_incident_timeline",
]
