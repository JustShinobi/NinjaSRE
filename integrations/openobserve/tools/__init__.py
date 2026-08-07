"""OpenObserve's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
OpenObserve has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.openobserve.tools.log_statistics import openobserve_log_statistics
from integrations.openobserve.tools.sample_logs import openobserve_sample_logs

__all__ = [
    "openobserve_log_statistics",
    "openobserve_sample_logs",
]
