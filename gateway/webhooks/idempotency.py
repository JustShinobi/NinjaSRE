"""Ingestion is idempotent on a source-provided event identifier, where one exists (FR-022).

Distinct from deduplication (``dedup.py``). Deduplication decides whether two
*different* alert payloads describe the same incident; idempotency decides
whether *this exact payload* has already been processed — a receiver retrying
a webhook after a slow response, or two load balancer paths delivering the
same delivery twice. The second case gets acknowledged and dropped with no
further effect, not linked: nothing new happened.

**The window is shorter than the deduplication one, and that is the whole
relationship between them.** This one bounds an HTTP retry, which happens in
seconds; deduplication bounds "the same problem, reported again", which happens
in minutes. A notification arriving after this window and inside that one is
therefore linked to the open investigation rather than answered as a duplicate
and forgotten — which is what a re-notified Alertmanager group needs, and what
it could not get while the two windows were the same length.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from config.constants.surfaces import WEBHOOK_DELIVERY_RETRY_WINDOW_SECONDS


@dataclass(slots=True)
class IdempotencyIndex:
    """Source-scoped event ids already processed, within a bounded window."""

    window_seconds: float = WEBHOOK_DELIVERY_RETRY_WINDOW_SECONDS
    clock: Callable[[], float] = time.monotonic
    _seen: dict[str, float] = field(default_factory=dict)

    def already_processed(self, source: str, event_id: str) -> bool:
        """Return whether ``event_id`` from ``source`` was already ingested.

        An empty ``event_id`` never counts as seen: a source with no stable
        event identifier gets no idempotency, not a false one keyed on
        nothing.
        """
        if not event_id:
            return False
        key = f"{source}:{event_id}"
        recorded_at = self._seen.get(key)
        if recorded_at is None:
            return False
        if self.clock() - recorded_at > self.window_seconds:
            del self._seen[key]
            return False
        return True

    def record(self, source: str, event_id: str) -> None:
        """Remember that ``event_id`` from ``source`` has been processed."""
        if not event_id:
            return
        self._seen[f"{source}:{event_id}"] = self.clock()


__all__ = ["IdempotencyIndex"]
