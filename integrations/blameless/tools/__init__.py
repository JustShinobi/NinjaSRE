"""Blameless's agent-callable capabilities.

3, and the set is the methodology rather than the API surface.
Blameless has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.blameless.tools.acknowledge_incident import blameless_acknowledge_incident
from integrations.blameless.tools.incident_statistics import blameless_incident_statistics
from integrations.blameless.tools.incident_timeline import blameless_incident_timeline

__all__ = [
    "blameless_acknowledge_incident",
    "blameless_incident_statistics",
    "blameless_incident_timeline",
]
