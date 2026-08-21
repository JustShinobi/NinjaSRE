"""PagerDuty's agent-callable capabilities.

3, and the set is the methodology rather than the API surface.
PagerDuty has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.pagerduty.tools.acknowledge_incident import pagerduty_acknowledge_incident
from integrations.pagerduty.tools.incident_statistics import pagerduty_incident_statistics
from integrations.pagerduty.tools.incident_timeline import pagerduty_incident_timeline

__all__ = [
    "pagerduty_acknowledge_incident",
    "pagerduty_incident_statistics",
    "pagerduty_incident_timeline",
]
