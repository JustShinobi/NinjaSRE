"""Tempo's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
Tempo has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.tempo.tools.slow_traces import tempo_slow_traces
from integrations.tempo.tools.trace_statistics import tempo_trace_statistics

__all__ = [
    "tempo_slow_traces",
    "tempo_trace_statistics",
]
