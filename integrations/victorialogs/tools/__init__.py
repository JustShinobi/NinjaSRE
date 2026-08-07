"""VictoriaLogs's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
VictoriaLogs has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.victorialogs.tools.log_statistics import victorialogs_log_statistics
from integrations.victorialogs.tools.sample_logs import victorialogs_sample_logs

__all__ = [
    "victorialogs_log_statistics",
    "victorialogs_sample_logs",
]
