"""Asking Prometheus one expression, in the shape a signal source expects.

``PrometheusClient`` speaks the vendor's paging vocabulary; a signal source
wants a list of series. This is the sentence between them, and it is a separate
object rather than a method on the client for the reason the client's own
docstring gives about reads: the client is what talks to the vendor, and what a
particular consumer wants out of the answer is that consumer's business.

**An instant, not a range.** A signal is one number at one moment. Asking the
range endpoint for it means inventing a window, which is a different question
with a different answer — and a 400 when the window is left out.
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
        return await self.client.query_instant(expression)


__all__ = ["PrometheusMetrics"]
