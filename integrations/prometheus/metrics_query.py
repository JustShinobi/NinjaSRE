"""Asking Prometheus one expression, in the shape a signal source expects.

``PrometheusClient`` speaks the vendor's paging vocabulary; a signal source
wants a list of series. This is the sentence between them, and it is a separate
object rather than a method on the client for the reason the client's own
docstring gives about reads: the client is what talks to the vendor, and what a
particular consumer wants out of the answer is that consumer's business.

**Truncation is reported, never hidden.** A page walk that stopped early would
otherwise reach a detector as "these are the guests", and a guest missing from a
result reads exactly like a guest with nothing to say.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from integrations.prometheus.client import PrometheusClient
from platform.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PrometheusMetrics:
    """Answers one PromQL expression with the series Prometheus returned."""

    client: PrometheusClient

    async def evaluate(self, expression: str) -> Sequence[Mapping[str, Any]]:
        """Return the ``result`` list for ``expression``."""
        pages = await self.client.query_metric(expression)
        if pages.truncated:
            logger.warning("prometheus.query_truncated", expression=expression)
        return pages.items


__all__ = ["PrometheusMetrics"]
