"""A window over the signal history, and what can be read off one.

Every detector reads exactly this: the samples of one signal about one resource
between two instants. Making that a value rather than a query result is what
makes evaluation pure — a window can be built from stored history as easily as
from a live read, which is the whole of how a detector is replayed against what
actually happened.

**A window knows whether it is complete.** ``covers`` is the difference between
"nothing crossed the threshold" and "we have not been watching long enough to
say". A detector that required a condition to hold for ten minutes and fired
after seeing two samples from the last thirty seconds would be firing on a
window it does not have, and the operator would never know which of the two it
was.

**Silence is measured from the last sample, not from the window.** A window with
no samples in it says nothing on its own: the source may have stopped, or the
resource may be new, or nobody may be watching it. ``silence`` therefore takes
the newest sample *whenever* it was taken, and returns ``None`` when there has
never been one — because "it stopped" and "it never started" are different
facts and only one of them is an incident.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from platform.persistence.ports.signal_store import Signal

#: Identifies one series: one signal name, about one resource.
SeriesKey = tuple[str, str]


@dataclass(frozen=True, slots=True)
class SignalWindow:
    """The samples of one signal about one resource, between two instants.

    ``samples`` is oldest first, matching the store's own order, because a rate
    of change computed over a reversed window has the right magnitude and the
    wrong sign.
    """

    name: str
    resource_id: str
    opened_at: datetime
    closed_at: datetime
    samples: tuple[Signal, ...] = ()
    #: The newest sample of this series *whenever* it was taken, which is what
    #: makes silence answerable from a window that is itself empty.
    last_seen: Signal | None = None

    @property
    def key(self) -> SeriesKey:
        """Return the series this window is over."""
        return (self.name, self.resource_id)

    @property
    def is_empty(self) -> bool:
        """Return whether the window holds no samples at all."""
        return not self.samples

    @property
    def newest(self) -> Signal | None:
        """Return the last sample inside the window, or ``None``."""
        return self.samples[-1] if self.samples else None

    @property
    def oldest(self) -> Signal | None:
        """Return the first sample inside the window, or ``None``."""
        return self.samples[0] if self.samples else None

    @property
    def values(self) -> tuple[float, ...]:
        """Return the numeric values, in order."""
        return tuple(sample.value for sample in self.samples)

    @property
    def states(self) -> tuple[str, ...]:
        """Return the state words, in order."""
        return tuple(sample.state for sample in self.samples)

    def covers(self, seconds: int) -> bool:
        """Return whether the samples actually span ``seconds`` of observation.

        Two samples a second apart do not cover ten minutes however long the
        window was asked for. This is what separates "the condition held" from
        "we have not watched long enough to know", and a detector that skipped
        it would fire on its first tick after a restart.

        The second clause is not a loophole, it is arithmetic. A source
        reporting every minute over a five-minute window contributes samples
        spanning four minutes at best, because the fifth would have to land
        exactly on the boundary; requiring the full span would mean a detector
        whose duration matches its source's interval could never fire at all. So
        a window is also covered when its oldest sample is the first one *after*
        the window opened, within one of that source's own intervals.
        """
        if seconds <= 0:
            return not self.is_empty
        oldest, newest = self.oldest, self.newest
        if oldest is None or newest is None:
            return False
        if newest.observed_at - oldest.observed_at >= timedelta(seconds=seconds):
            return True
        grace = timedelta(seconds=oldest.interval_seconds)
        return grace > timedelta(0) and oldest.observed_at - self.opened_at <= grace

    def silence(self, now: datetime) -> timedelta | None:
        """Return how long this series has been quiet, or ``None`` if it never spoke.

        ``None`` rather than an enormous duration. A resource nobody has ever
        measured is not a resource that stopped reporting, and an absence
        detector that treated the two the same would fire on every resource an
        integration does not cover.
        """
        if self.last_seen is None:
            return None
        return now - self.last_seen.observed_at

    def is_silent(self, now: datetime, *, tolerance_seconds: int = 0) -> bool:
        """Return whether the source of this series has stopped reporting."""
        return self.last_seen is not None and self.last_seen.is_silent_at(
            now, tolerance_seconds=tolerance_seconds
        )


def windows(
    samples: Iterable[Signal],
    *,
    opened_at: datetime,
    closed_at: datetime,
    latest: Iterable[Signal] = (),
) -> tuple[SignalWindow, ...]:
    """Return one window per series, from a flat list of samples.

    ``latest`` carries the newest sample per series *from outside the window*,
    which is how a series that has gone quiet still produces a window rather than
    disappearing from the result. A series that appears only in ``latest`` gets
    an empty window with its last sample attached — which is exactly the shape an
    absence condition reads.
    """
    grouped: dict[SeriesKey, list[Signal]] = {}
    for sample in samples:
        grouped.setdefault((sample.name, sample.resource_id), []).append(sample)

    newest: dict[SeriesKey, Signal] = {}
    for sample in latest:
        key = (sample.name, sample.resource_id)
        held = newest.get(key)
        if held is None or sample.observed_at > held.observed_at:
            newest[key] = sample
    for key, series in grouped.items():
        candidate = max(series, key=lambda sample: sample.observed_at)
        held = newest.get(key)
        if held is None or candidate.observed_at > held.observed_at:
            newest[key] = candidate

    return tuple(
        SignalWindow(
            name=name,
            resource_id=resource_id,
            opened_at=opened_at,
            closed_at=closed_at,
            samples=tuple(
                sorted(
                    grouped.get((name, resource_id), ()),
                    key=lambda sample: (sample.observed_at, sample.signal_id),
                )
            ),
            last_seen=newest.get((name, resource_id)),
        )
        for name, resource_id in sorted(set(grouped) | set(newest))
    )


__all__ = ["SeriesKey", "SignalWindow", "windows"]
