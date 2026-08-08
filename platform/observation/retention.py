"""Keeping signals exactly as long as some detector can still reach them.

Retention here is derived, not configured. The other data classes in
``platform/persistence/ports/retention.py`` are kept for days because somebody
decided how long an operator wants to be able to look back; a signal is kept
because a detector's window still reaches it, and that is a fact about the
declarations rather than a preference.

The consequence is the point. An operator who lengthens a detector's window from
ten minutes to an hour does not also have to remember to lengthen retention — if
they did, the detector would silently never fire and there would be nothing to
distinguish that from an estate with nothing wrong. And an operator who deletes
their last long-window detector gets the table back without doing anything.

The sweep is bounded rather than complete on purpose: it deletes what is past the
horizon and reports the count, and a deployment that has accumulated more than
one pass can remove gets the rest on the next tick. A sweep that had to finish
would be a sweep that holds a transaction open across the whole table.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from platform.observability.logging import get_logger
from platform.observation.detectors.model import DetectorDeclaration
from platform.persistence.ports.signal_store import SignalStore, retention_seconds

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SignalRetention:
    """The horizon this deployment's detectors imply, and the sweep that applies it."""

    detectors: tuple[DetectorDeclaration, ...] = ()

    @property
    def horizon_seconds(self) -> int:
        """Return how far back signals are kept, given these detectors.

        Every declared window counts, including the ones on disabled detectors:
        an operator who switches a detector back on wants it to have history to
        read, and re-enabling something that then cannot fire for an hour is the
        surprise this avoids.
        """
        return retention_seconds(_declared_windows(self.detectors))

    def cutoff(self, now: datetime) -> datetime:
        """Return the instant before which a sample is no longer reachable."""
        return now - timedelta(seconds=self.horizon_seconds)

    async def sweep(self, signals: SignalStore, *, now: datetime) -> int:
        """Delete the samples no detector can still reach and return the count."""
        cutoff = self.cutoff(now)
        removed = await signals.prune(before=cutoff)
        if removed:
            logger.info(
                "observation.signals_pruned",
                removed=removed,
                horizon_seconds=self.horizon_seconds,
                cutoff=cutoff.isoformat(),
            )
        return removed


def _declared_windows(detectors: Iterable[DetectorDeclaration]) -> tuple[int, ...]:
    """Return every window length the declarations imply.

    Both the firing duration and the recovery duration, because a detector that
    can fire and never clear is worse than one that cannot fire: the incident
    stays open, and the operator learns to close it by hand.
    """
    lengths: list[int] = []
    for detector in detectors:
        lengths.append(detector.for_seconds)
        lengths.append(detector.recovery_seconds)
    return tuple(lengths)


__all__ = ["SignalRetention"]
