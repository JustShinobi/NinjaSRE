"""Two probes that ask a signal source whether its answers are worth anything.

The permission probes beside this module establish that a call is *allowed*.
That is the whole question for a vendor whose reads are exact — an issue tracker
either returns the ticket or refuses. It is not the question for a store of
time-ordered data, where the two most expensive failures both answer 200.

**A store that holds nothing for the window that matters.** Every scrape target
down, retention cut to an hour, the query pointed at a tenant nobody writes to:
all of them return a well-formed body with an empty result set. An investigation
that reaches this source concludes that nothing happened, with citations. This
is the failure the whole family exists for, so it gets a state of its own —
``EMPTY_WINDOW``, distinct from denied and from unreachable — and advice that
names what to check rather than restating that it failed.

**A store whose clock disagrees with the platform's.** Correlation is the only
reason to read four sources instead of one, and correlation across a thirty-
second offset puts cause after effect. Measured rather than assumed, reported
with the offset, and reported as *degraded* rather than as broken: a source
whose data is good and whose clock is wrong is still worth reading, by somebody
who has been told.

**An empty answer is sometimes the correct answer.** An alert router holding no
alerts is an alert router doing its job. So a probe declares what emptiness
means for its vendor, and a source whose ordinary state is empty is never
reported as broken for being in it — which is what stops an operator learning to
ignore the check.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from enum import StrEnum
from typing import Any

from config.constants.signals import (
    SOURCE_CLOCK_SKEW_TOLERANCE_SECONDS,
    VERIFY_WINDOW_MINUTES,
)
from integrations._base.errors import ErrorCategory, IntegrationError


@dataclass(frozen=True, slots=True)
class DataWindow:
    """The recent stretch of time a verification read asks about.

    Carries the instants and every spelling of them a vendor asks for, because
    the alternative is each of six verifiers formatting its own — and the one
    that gets it wrong returns an empty result that reads exactly like an empty
    store.
    """

    start: datetime
    end: datetime

    @classmethod
    def ending_at(cls, now: datetime, *, minutes: int = VERIFY_WINDOW_MINUTES) -> DataWindow:
        """Return the window of ``minutes`` that ends at ``now``."""
        return cls(start=now - timedelta(minutes=minutes), end=now)

    @property
    def minutes(self) -> int:
        """Return how long the window is, in whole minutes."""
        return int((self.end - self.start).total_seconds() // 60)

    @property
    def start_rfc3339(self) -> str:
        """Return the start as an ISO-8601 instant, for a vendor that reads them."""
        return self.start.isoformat().replace("+00:00", "Z")

    @property
    def end_rfc3339(self) -> str:
        """Return the end as an ISO-8601 instant."""
        return self.end.isoformat().replace("+00:00", "Z")

    @property
    def start_epoch_seconds(self) -> str:
        """Return the start as whole seconds since the epoch."""
        return str(int(self.start.timestamp()))

    @property
    def end_epoch_seconds(self) -> str:
        """Return the end as whole seconds since the epoch."""
        return str(int(self.end.timestamp()))

    @property
    def start_epoch_milliseconds(self) -> str:
        """Return the start in milliseconds, which is what some trace stores index in."""
        return str(int(self.start.timestamp() * 1_000))

    @property
    def end_epoch_milliseconds(self) -> str:
        """Return the end in milliseconds."""
        return str(int(self.end.timestamp() * 1_000))

    @property
    def start_epoch_microseconds(self) -> str:
        """Return the start in microseconds, which is what some stores index in."""
        return str(int(self.start.timestamp() * 1_000_000))

    @property
    def end_epoch_microseconds(self) -> str:
        """Return the end in microseconds."""
        return str(int(self.end.timestamp() * 1_000_000))

    @property
    def start_epoch_nanoseconds(self) -> str:
        """Return the start in nanoseconds, which is what some log stores index in."""
        return str(int(self.start.timestamp() * 1_000_000_000))

    @property
    def end_epoch_nanoseconds(self) -> str:
        """Return the end in nanoseconds."""
        return str(int(self.end.timestamp() * 1_000_000_000))


class EmptyWindow(StrEnum):
    """What an empty answer proves about a particular vendor."""

    #: A store that should always hold something. Empty means it stopped
    #: collecting, and that is a finding.
    BROKEN = "broken"

    #: A source whose ordinary state is holding nothing — an alert router with
    #: no alerts, a trace store for a deployment nobody has instrumented. Empty
    #: is a real answer, and reporting it as a fault trains an operator to
    #: ignore the check.
    EXPECTED = "expected"


class WindowState(StrEnum):
    """What one windowed read established about a source's data."""

    #: The read went through and the source held something.
    RETURNED = "returned"
    #: The read went through and the source held nothing across the window.
    EMPTY_WINDOW = "empty_window"
    #: The vendor refused the read for authorisation reasons.
    DENIED = "denied"
    #: The read failed for a reason that says nothing about the data.
    INCONCLUSIVE = "inconclusive"
    #: Not attempted, because the credential itself was rejected first.
    UNCHECKED = "unchecked"


class SkewState(StrEnum):
    """What one clock reading established about a source's sense of time."""

    #: The source's clock is close enough for correlation to mean something.
    IN_TOLERANCE = "in_tolerance"
    #: It is not, and every timestamp this source contributes is offset.
    OUT_OF_TOLERANCE = "out_of_tolerance"
    #: The source does not say what time it thinks it is.
    UNREPORTED = "unreported"
    #: Not attempted, because the credential itself was rejected first.
    UNCHECKED = "unchecked"


#: One windowed read: given the transport, who the call is for, and the window,
#: return how many series or lines came back. A count rather than the records
#: themselves, because verification must not pull an incident's worth of data
#: through a setup screen — and because the only thing being asked is whether
#: the answer was empty.
WindowRead = Callable[[Any, Any, DataWindow], Awaitable[int]]

#: One clock reading: return what instant the source believes it is, or ``None``
#: when it does not say. ``None`` is a first-class answer here rather than an
#: error, because "this vendor publishes no clock" is a fact about the vendor.
ClockRead = Callable[[Any, Any], Awaitable[datetime | None]]


@dataclass(frozen=True, slots=True)
class DataWindowOutcome:
    """What one windowed read found, and how to read it."""

    state: WindowState
    window: DataWindow
    rows: int
    description: str
    empty_means: EmptyWindow = EmptyWindow.BROKEN
    detail: str = ""
    advice: str = ""

    @property
    def window_minutes(self) -> int:
        """Return the window this read covered, in whole minutes."""
        return self.window.minutes

    @property
    def usable(self) -> bool:
        """Return whether this source can answer a question about the recent past.

        An expected-empty source is usable while empty; a store that should hold
        something and does not is exactly as useful as one that is down, and
        considerably harder to notice.
        """
        if self.state is WindowState.RETURNED:
            return True
        if self.state is WindowState.EMPTY_WINDOW:
            return self.empty_means is EmptyWindow.EXPECTED
        return self.state is WindowState.UNCHECKED or self.state is WindowState.INCONCLUSIVE

    @property
    def is_finding(self) -> bool:
        """Return whether this outcome is something an operator has to act on."""
        if self.state is WindowState.EMPTY_WINDOW:
            return self.empty_means is EmptyWindow.BROKEN
        return self.state is WindowState.DENIED

    def to_record(self) -> dict[str, object]:
        """Return the JSON-serialisable form a CLI, a console, or CI renders."""
        return {
            "state": self.state.value,
            "window_minutes": self.window_minutes,
            "window_start": self.window.start_rfc3339,
            "window_end": self.window.end_rfc3339,
            "rows": self.rows,
            "probe": self.description,
            "empty_means": self.empty_means.value,
            "usable": self.usable,
            "detail": self.detail,
            "advice": self.advice,
        }


@dataclass(frozen=True, slots=True)
class ClockSkewOutcome:
    """How far a source's clock is from the platform's, and whether that matters."""

    state: SkewState
    tolerance_seconds: float
    description: str
    offset_seconds: float | None = None
    source_time: datetime | None = None
    detail: str = ""

    @property
    def degraded(self) -> bool:
        """Return whether this source's timestamps cannot be correlated as they stand."""
        return self.state is SkewState.OUT_OF_TOLERANCE

    def to_record(self) -> dict[str, object]:
        """Return the JSON-serialisable form a CLI, a console, or CI renders."""
        return {
            "state": self.state.value,
            "offset_seconds": self.offset_seconds,
            "tolerance_seconds": self.tolerance_seconds,
            "source_time": None if self.source_time is None else self.source_time.isoformat(),
            "probe": self.description,
            "degraded": self.degraded,
            "detail": self.detail,
        }


#: How a classified failure reads as a statement about the data behind it. Only
#: ``PERMISSION`` says anything: everything else stopped the call before the
#: store had a chance to answer, and reporting "no data" for a proxy that was
#: down would be the empty-window failure committed by the check for it.
_WINDOW_STATES: dict[ErrorCategory, WindowState] = {
    ErrorCategory.PERMISSION: WindowState.DENIED,
    ErrorCategory.AUTH: WindowState.UNCHECKED,
    ErrorCategory.NOT_FOUND: WindowState.INCONCLUSIVE,
    ErrorCategory.RATE_LIMITED: WindowState.INCONCLUSIVE,
    ErrorCategory.TRANSIENT: WindowState.INCONCLUSIVE,
    ErrorCategory.UNAVAILABLE: WindowState.INCONCLUSIVE,
    ErrorCategory.INVALID_REQUEST: WindowState.INCONCLUSIVE,
}


@dataclass(frozen=True, slots=True)
class DataWindowProbe:
    """The cheapest read that proves a source is holding recent data.

    ``advice`` is not optional and not a default. The whole value of separating
    ``EMPTY_WINDOW`` from every other failure is that it has a different remedy,
    and a probe that reports the state without naming the remedy has done the
    detection and left the useful half out.
    """

    description: str
    read: WindowRead
    advice: str
    empty_means: EmptyWindow = EmptyWindow.BROKEN

    def __post_init__(self) -> None:
        if not self.description.strip():
            raise ValueError(
                "a window probe must say what it read. An empty result from an unnamed "
                "query is a result nobody can interpret, which is the failure this probe "
                "exists to prevent."
            )
        if not self.advice.strip():
            raise ValueError(
                "a window probe must carry the advice for an empty window. Reporting the "
                "state without naming what to check leaves the operator exactly where the "
                "status code left them."
            )

    async def run(self, transport: Any, context: Any, *, window: DataWindow) -> DataWindowOutcome:
        """Make the read and return what it established about the source's data."""
        try:
            rows = await self.read(transport, context, window)
        except IntegrationError as error:
            return DataWindowOutcome(
                state=_WINDOW_STATES[error.category],
                window=window,
                rows=0,
                description=self.description,
                empty_means=self.empty_means,
                detail=str(error),
                advice=self.advice,
            )

        if rows > 0:
            return DataWindowOutcome(
                state=WindowState.RETURNED,
                window=window,
                rows=rows,
                description=self.description,
                empty_means=self.empty_means,
                detail=f"{rows} series or line(s) over the last {window.minutes} minutes",
                advice=self.advice,
            )
        return DataWindowOutcome(
            state=WindowState.EMPTY_WINDOW,
            window=window,
            rows=0,
            description=self.description,
            empty_means=self.empty_means,
            detail=f"nothing at all over the last {window.minutes} minutes",
            advice=self.advice,
        )

    def unchecked(self, window: DataWindow) -> DataWindowOutcome:
        """Return the outcome for a source whose credential was rejected first."""
        return DataWindowOutcome(
            state=WindowState.UNCHECKED,
            window=window,
            rows=0,
            description=self.description,
            empty_means=self.empty_means,
            detail="the credential was rejected before the data could be read",
            advice=self.advice,
        )


@dataclass(frozen=True, slots=True)
class ClockSkewProbe:
    """Reads what time a source thinks it is, and compares it with the platform's."""

    description: str
    read: ClockRead
    tolerance_seconds: float = SOURCE_CLOCK_SKEW_TOLERANCE_SECONDS

    def __post_init__(self) -> None:
        if not self.description.strip():
            raise ValueError(
                "a clock probe must say where it read the source's time. Whether it came "
                "from a response header or from a status endpoint decides how much of the "
                "measured offset is the network."
            )

    async def run(self, transport: Any, context: Any, *, now: datetime) -> ClockSkewOutcome:
        """Return how far this source's clock is from ``now``."""
        try:
            reported = await self.read(transport, context)
        except IntegrationError as error:
            return ClockSkewOutcome(
                state=SkewState.UNREPORTED,
                tolerance_seconds=self.tolerance_seconds,
                description=self.description,
                detail=str(error),
            )

        if reported is None:
            return ClockSkewOutcome(
                state=SkewState.UNREPORTED,
                tolerance_seconds=self.tolerance_seconds,
                description=self.description,
                detail=(
                    "this source does not report its own time, so nothing here says whether "
                    "its timestamps line up with the platform's"
                ),
            )

        offset = (reported - now).total_seconds()
        within = abs(offset) <= self.tolerance_seconds
        return ClockSkewOutcome(
            state=SkewState.IN_TOLERANCE if within else SkewState.OUT_OF_TOLERANCE,
            tolerance_seconds=self.tolerance_seconds,
            description=self.description,
            offset_seconds=offset,
            source_time=reported,
            detail=(
                f"the source is {offset:+.1f}s from the platform's clock, "
                f"{'inside' if within else 'outside'} the {self.tolerance_seconds:.1f}s tolerance"
            ),
        )

    def unchecked(self) -> ClockSkewOutcome:
        """Return the outcome for a source whose credential was rejected first."""
        return ClockSkewOutcome(
            state=SkewState.UNCHECKED,
            tolerance_seconds=self.tolerance_seconds,
            description=self.description,
            detail="the credential was rejected before the clock could be read",
        )


def http_date(value: str) -> datetime | None:
    """Return the instant an HTTP ``Date`` header names, or ``None``.

    Every one of these vendors answers HTTP, and HTTP carries the server's clock
    on every response — which makes this the one clock reading that costs no
    extra call and works for a vendor that publishes no status endpoint.
    Unparseable is ``None`` rather than an exception: a proxy that rewrote the
    header is not a verification failure.
    """
    if not value.strip():
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def client_window_probe[Client](
    *,
    description: str,
    build: Callable[[Any, Any], Client],
    read: Callable[[Client, DataWindow], Awaitable[int]],
    advice: str,
    empty_means: EmptyWindow = EmptyWindow.BROKEN,
) -> DataWindowProbe:
    """Return a window probe that builds a client and makes one read with it.

    The same shape ``client_probe`` has, and for the same reason: a verifier
    that constructs its own client per probe is one retry policy away from a
    verification run that takes four minutes.
    """

    async def probe(transport: Any, context: Any, window: DataWindow) -> int:
        return await read(build(transport, context), window)

    return DataWindowProbe(
        description=description, read=probe, advice=advice, empty_means=empty_means
    )


def client_clock_probe[Client](
    *,
    description: str,
    build: Callable[[Any, Any], Client],
    call: Callable[[Client], Awaitable[Any]],
    tolerance_seconds: float = SOURCE_CLOCK_SKEW_TOLERANCE_SECONDS,
) -> ClockSkewProbe:
    """Return a clock probe that reads the ``Date`` header off one vendor answer."""

    async def probe(transport: Any, context: Any) -> datetime | None:
        response = await call(build(transport, context))
        headers = getattr(response, "headers", {}) or {}
        for key, value in headers.items():
            if key.lower() == "date":
                return http_date(str(value))
        return None

    return ClockSkewProbe(description=description, read=probe, tolerance_seconds=tolerance_seconds)


__all__ = [
    "ClockRead",
    "ClockSkewOutcome",
    "ClockSkewProbe",
    "DataWindow",
    "DataWindowOutcome",
    "DataWindowProbe",
    "EmptyWindow",
    "SkewState",
    "WindowRead",
    "WindowState",
    "client_clock_probe",
    "client_window_probe",
    "http_date",
]
