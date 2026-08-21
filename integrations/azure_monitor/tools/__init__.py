"""Azure Monitor's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
Azure Monitor has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.azure_monitor.tools.log_statistics import azure_monitor_log_statistics
from integrations.azure_monitor.tools.sample_logs import azure_monitor_sample_logs

__all__ = [
    "azure_monitor_log_statistics",
    "azure_monitor_sample_logs",
]
