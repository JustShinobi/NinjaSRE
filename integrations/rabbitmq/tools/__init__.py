"""RabbitMQ's agent-callable capabilities.

2, and the set is the methodology rather than the API surface.
RabbitMQ has many more endpoints than this; what an investigation needs is
the shape of the answer and then a handful of records, in that order, and a
package offering both makes the wrong order possible while a package offering
only the second makes it inevitable.

Discovery walks this package, so adding a capability is one module and no edit
anywhere else.
"""

from __future__ import annotations

from integrations.rabbitmq.tools.pipeline_health import rabbitmq_pipeline_health
from integrations.rabbitmq.tools.recent_failures import rabbitmq_recent_failures

__all__ = [
    "rabbitmq_pipeline_health",
    "rabbitmq_recent_failures",
]
