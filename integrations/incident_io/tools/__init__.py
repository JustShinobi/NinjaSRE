"""incident.io's agent-callable capabilities.

3, and the set is the methodology rather than the API surface.
incident.io has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.incident_io.tools.acknowledge_incident import incident_io_acknowledge_incident
from integrations.incident_io.tools.incident_statistics import incident_io_incident_statistics
from integrations.incident_io.tools.incident_timeline import incident_io_incident_timeline

__all__ = [
    "incident_io_acknowledge_incident",
    "incident_io_incident_statistics",
    "incident_io_incident_timeline",
]
