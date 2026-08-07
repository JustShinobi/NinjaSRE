"""Kafka's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
Kafka has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.kafka.tools.pipeline_health import kafka_pipeline_health
from integrations.kafka.tools.recent_failures import kafka_recent_failures

__all__ = [
    "kafka_pipeline_health",
    "kafka_recent_failures",
]
