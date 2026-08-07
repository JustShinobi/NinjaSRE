"""Coralogix's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
Coralogix has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.coralogix.tools.log_statistics import coralogix_log_statistics
from integrations.coralogix.tools.sample_logs import coralogix_sample_logs

__all__ = [
    "coralogix_log_statistics",
    "coralogix_sample_logs",
]
