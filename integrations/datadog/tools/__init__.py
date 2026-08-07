"""Datadog's agent-callable capabilities.

Two, and the pair is the methodology rather than the API surface. Datadog has
dozens of endpoints; what an investigation needs is the shape of the logs and
then a handful of the lines, in that order, and a package offering both makes
the wrong order possible while a package offering only the second makes it
inevitable.

Discovery walks this package, so adding a capability here is one module and no
edit anywhere else.
"""

from __future__ import annotations

from integrations.datadog.tools.log_statistics import datadog_log_statistics
from integrations.datadog.tools.sample_logs import datadog_sample_logs

__all__ = [
    "datadog_log_statistics",
    "datadog_sample_logs",
]
