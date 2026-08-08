"""What the deployment has observed about its estate, over time.

The fourteenth port, and the first whose records are *samples* rather than
facts. That difference decides everything below.

**A signal is immutable and its identity is derived.** One name, about one
resource, at one instant, from one source. The key is derived from those four
rather than generated, so a poller that ran twice — a retry, a second replica,
a restart mid-append — writes the same row rather than a second sample that
would make an average wrong.

**Silence is a reading.** The most important detector in a small estate is "the
thing that was reporting has stopped", and a store that only answers "what
samples do you have" cannot express it: a query over the last five minutes
returns nothing both for a source that died and for a resource nobody watches.
``latest`` therefore exists beside ``window`` and returns the newest sample
*whenever* it was taken, so the caller can subtract and get an age. The
interpretation — how late is too late — belongs to the detector, and the
interval the source promised is carried on the sample so the detector has
something to compare against.

**Retention is derived from the detectors, not configured beside them.** A
signal is worth keeping exactly as long as some detector's window still reaches
it. ``retention_seconds`` is that rule, written once here, because an operator
who lengthened a window and forgot to lengthen retention would own a detector
that can never fire — and would have no way to tell that from a quiet estate.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol, runtime_checkable

from config.constants.observation import (
    DEFAULT_SIGNAL_RETENTION_SECONDS,
    MAX_SIGNAL_PAGE_SIZE,
    SIGNAL_SILENCE_TOLERANCE_INTERVALS,
)
from platform.persistence.errors import BoundExceeded


class SignalKind(StrEnum):
    """What sort of value a signal carries. There is no third member.

    Numbers are compared; states are matched. Keeping them apart in the type
    rather than in a convention is what lets a threshold condition refuse a
    state signal at declaration time instead of at three in the morning.
    """

    NUMBER = "number"
    STATE = "state"


@dataclass(frozen=True, slots=True)
class Signal:
    """One named, typed, timestamped observation about one resource.

    ``interval_seconds`` is the source's promise about how often this will
    arrive, and it is on the sample rather than in a table beside it because a
    detector reading a window has the samples and nothing else. Zero means the
    source made no promise, which is a real answer: nothing can be concluded
    from the silence of something that never said it would speak.
    """

    signal_id: str
    name: str
    resource_id: str
    source: str
    kind: SignalKind
    observed_at: datetime
    value: float = 0.0
    state: str = ""
    interval_seconds: int = 0
    labels: Mapping[str, str] = field(default_factory=dict)

    def silent_for(self, now: datetime) -> timedelta:
        """Return how long it has been since this sample was taken."""
        return now - self.observed_at

    def is_silent_at(self, now: datetime, *, tolerance_seconds: int = 0) -> bool:
        """Return whether the source has missed enough reports to count as silent.

        A source that promised nothing is never silent. Anything else is silent
        once it is later than ``tolerance_seconds``, or — when the caller passes
        none — later than the tolerance intervals the deployment declares. One
        missed poll is a network hiccup; the default is three, because an
        absence detector that fired on the first would fire daily.
        """
        if self.interval_seconds <= 0:
            return False
        allowed = tolerance_seconds or (self.interval_seconds * SIGNAL_SILENCE_TOLERANCE_INTERVALS)
        return self.silent_for(now) > timedelta(seconds=allowed)


@dataclass(frozen=True, slots=True)
class SignalQuery:
    """A window over the signal history, in the dimensions a detector reads it by.

    Empty tuples mean "no filter on this dimension" rather than "match nothing",
    for the reason ``EstateQuery`` says: it is the only reading that composes
    when a caller builds a query out of optional inputs.
    """

    names: tuple[str, ...] = ()
    resource_ids: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    since: datetime | None = None
    until: datetime | None = None
    limit: int = 500


def signal_key(name: str, resource_id: str, observed_at: datetime) -> str:
    """Return the identifier one observation of one signal at one instant gets.

    Deterministic, for the reason the scheduler's fire key is: two replicas that
    both polled the same source at the same instant derive the same key, and the
    second write lands on the first rather than beside it. A stored average over
    a window is only meaningful if a retry cannot double a sample.
    """
    return f"{name}@{resource_id}@{observed_at.isoformat()}"


def check_signal_limit(limit: int) -> int:
    """Return ``limit``, or raise if it exceeds the signal page bound.

    Its own bound rather than the shared query one: a detector's window is read
    in a single page on purpose, because a verdict that depended on paging would
    depend on how many samples happened to arrive.
    """
    if limit > MAX_SIGNAL_PAGE_SIZE:
        raise BoundExceeded(
            parameter="limit",
            requested=limit,
            limit=MAX_SIGNAL_PAGE_SIZE,
            constant="MAX_SIGNAL_PAGE_SIZE",
        )
    if limit < 1:
        raise ValueError(f"limit must be at least 1, got {limit}.")
    return limit


def retention_seconds(window_seconds: Iterable[int]) -> int:
    """Return how long signals must be kept for detectors with these windows.

    The longest window any detector declares, and no longer — which is the whole
    of the retention rule and the reason it is a function of the declarations
    rather than a setting beside them. A deployment with no detectors keeps the
    shipped default, so the table is bounded before the first detector exists.
    """
    longest = max((seconds for seconds in window_seconds if seconds > 0), default=0)
    return longest or DEFAULT_SIGNAL_RETENTION_SECONDS


def matches(signal: Signal, query: SignalQuery) -> bool:
    """Return whether ``signal`` satisfies every filter ``query`` declares.

    Shared by both backends because it is *contract*: a name filter that matched
    a prefix in one backend and an exact string in the other would make a
    detector fire differently depending on where it ran.
    """
    if query.names and signal.name not in query.names:
        return False
    if query.resource_ids and signal.resource_id not in query.resource_ids:
        return False
    if query.sources and signal.source not in query.sources:
        return False
    if query.since is not None and signal.observed_at < query.since:
        return False
    return not (query.until is not None and signal.observed_at > query.until)


@runtime_checkable
class SignalStore(Protocol):
    """One organisation's observation history, inside one transaction."""

    async def append(self, signals: Sequence[Signal]) -> tuple[Signal, ...]:
        """Store ``signals`` and return them, replacing any with the same key.

        Idempotent by derived identity rather than by a check the caller makes:
        appending the same observation twice is one row, so a poller that
        retried has not doubled its own reading.
        """

    async def window(self, query: SignalQuery) -> tuple[Signal, ...]:
        """Return the samples matching ``query``, oldest first.

        Oldest first because that is the order a detector reads a window in —
        a rate of change computed over a reversed list is the same magnitude
        with the wrong sign. Raises ``BoundExceeded`` above
        ``MAX_SIGNAL_PAGE_SIZE``.
        """

    async def latest(
        self,
        *,
        names: tuple[str, ...] = (),
        resource_ids: tuple[str, ...] = (),
    ) -> tuple[Signal, ...]:
        """Return the newest sample per ``(name, resource)``, however old it is.

        Deliberately unbounded in time. This is the read that makes silence
        answerable: a window returns nothing both for a source that stopped and
        for a resource nobody watches, and those are different facts.
        """

    async def prune(self, *, before: datetime) -> int:
        """Delete samples observed before ``before`` and return how many went."""


__all__ = [
    "Signal",
    "SignalKind",
    "SignalQuery",
    "SignalStore",
    "check_signal_limit",
    "matches",
    "retention_seconds",
    "signal_key",
]
