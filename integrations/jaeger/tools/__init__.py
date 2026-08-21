"""Jaeger's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
Jaeger has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.jaeger.tools.slow_traces import jaeger_slow_traces
from integrations.jaeger.tools.trace_statistics import jaeger_trace_statistics

__all__ = [
    "jaeger_slow_traces",
    "jaeger_trace_statistics",
]
