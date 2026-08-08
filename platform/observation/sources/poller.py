"""Calling a source on its interval, and refusing to call it faster.

The poller is deliberately thin. It decides *whether* a source is due, asks it
once, checks what the call cost against what the source declared it may cost,
and derives an identity for every reading. Everything else — how the provider is
reached, what the measurement means — belongs to the source.

Two properties are worth stating because they are the ones a thicker poller
would lose.

**Detection adds no provider calls beyond the declared ones.** A source declares
an interval and a call budget; the poller enforces both and has no way to raise
either. A source that spent more calls than it declared is a bug in the source
and is reported as one, rather than being absorbed into somebody's provider bill.

**A failed poll raises.** It does not return an empty page. An empty page from a
healthy provider and an unreachable provider are opposite facts, and an absence
detector reading the resulting silence would blame the estate for an outage of
the integration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from platform.observability.logging import get_logger
from platform.observation.errors import ObservationBoundExceeded
from platform.observation.sources.port import (
    PollBudget,
    SignalDeclaration,
    SignalReader,
    as_signal,
)
from platform.persistence.ports.signal_store import Signal

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Poller:
    """One source, called no more often and no harder than it declared."""

    reader: SignalReader

    @property
    def declaration(self) -> SignalDeclaration:
        """Return what the source says about itself."""
        return self.reader.declaration

    def is_due(self, *, last_polled_at: datetime | None, now: datetime) -> bool:
        """Return whether this source may be called at ``now``.

        A source that has never been polled is always due. Everything else waits
        out its declared interval, which is the whole of the promise that
        detection adds no provider calls beyond the ones a source asked for.
        """
        if last_polled_at is None:
            return True
        return now - last_polled_at >= timedelta(seconds=self.declaration.interval_seconds)

    def calls_allowed_per_tick(self, *, tick_seconds: int) -> int:
        """Return how many calls the provider's own rate limit leaves for one tick.

        The provider's limit rather than ours, because the number that matters
        is the one the vendor enforces. A tick shorter than a minute gets a
        proportional share and never less than one — a rate limit that resolved
        to zero calls would silently disable the source.
        """
        per_minute = max(1, self.declaration.rate_limit_per_minute)
        return max(1, int(per_minute * tick_seconds / 60))

    async def poll(
        self,
        *,
        resource_ids: tuple[str, ...],
        now: datetime,
        budget: PollBudget | None = None,
    ) -> tuple[Signal, ...]:
        """Return the samples this source reports for ``resource_ids`` at ``now``.

        Raises ``ObservationBoundExceeded`` when the source spent more provider
        calls than it declared it would. Reported rather than absorbed: a source
        that quietly overspends is how a deployment discovers its own detection
        in a vendor's rate-limit dashboard.
        """
        allowance = budget or PollBudget.for_declaration(self.declaration)
        page = await self.reader.read(resource_ids=resource_ids, at=now, budget=allowance)

        if page.provider_calls > allowance.max_provider_calls:
            raise ObservationBoundExceeded(
                parameter=f"{self.declaration.source} provider calls per poll",
                requested=page.provider_calls,
                limit=allowance.max_provider_calls,
                constant="the source's own declared max_provider_calls",
            )

        readings = page.readings[: allowance.max_readings]
        if len(page.readings) > len(readings):
            logger.warning(
                "observation.poll_truncated",
                source=self.declaration.source,
                returned=len(page.readings),
                kept=len(readings),
            )

        return tuple(
            as_signal(
                reading,
                source=self.declaration.source,
                interval_seconds=self.declaration.interval_seconds,
                now=now,
            )
            for reading in readings
        )


__all__ = ["Poller"]
