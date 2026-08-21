"""Splunk's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
Splunk has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.splunk.tools.log_statistics import splunk_log_statistics
from integrations.splunk.tools.sample_logs import splunk_sample_logs

__all__ = [
    "splunk_log_statistics",
    "splunk_sample_logs",
]
