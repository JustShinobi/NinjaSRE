"""FireHydrant's agent-callable capabilities.

3, and the set is the methodology rather than the API surface.
FireHydrant has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.firehydrant.tools.acknowledge_incident import firehydrant_acknowledge_incident
from integrations.firehydrant.tools.incident_statistics import firehydrant_incident_statistics
from integrations.firehydrant.tools.incident_timeline import firehydrant_incident_timeline

__all__ = [
    "firehydrant_acknowledge_incident",
    "firehydrant_incident_statistics",
    "firehydrant_incident_timeline",
]
