"""Honeycomb's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
Honeycomb has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.honeycomb.tools.slow_traces import honeycomb_slow_traces
from integrations.honeycomb.tools.trace_statistics import honeycomb_trace_statistics

__all__ = [
    "honeycomb_slow_traces",
    "honeycomb_trace_statistics",
]
