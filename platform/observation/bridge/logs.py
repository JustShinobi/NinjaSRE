"""Reading a bounded slice of somebody else's logs, and saying exactly what was read.

An investigation asks for a guest's logs and gets an answer. The whole risk is
that the answer looks complete and is not — five hundred lines out of ten
thousand, or fifteen minutes out of an hour because the log system only keeps
ten. Either one produces a responder who concludes there was nothing in the
logs, which is the opposite of what happened.

So every answer here carries its own bound. Not in the configuration, not in a
log line: in the value the caller holds, beside the lines. ``complete`` is a
property somebody can assert on, and ``summary`` is the sentence a report
carries when it is false.

**Retention shorter than the window is a fact, not an error.** A Loki keeping an
hour asked for a day answers with the hour it has. What it must not do is answer
with the hour and let that read as a day, so the shortfall travels with the
result and the window in the answer is the window that was actually read.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from config.constants.observability_bridge import (
    DEFAULT_LOG_WINDOW_SECONDS,
    MAX_LOG_LINES,
    MAX_LOG_WINDOW_SECONDS,
)
from platform.observability.logging import get_logger
from platform.observation.bridge.errors import BridgeBoundExceeded, LogSourceUnreachable
from platform.observation.bridge.ports import LogLine, LogSource

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class LogVerification:
    """What one check established about a log source."""

    source: str
    reachable: bool
    retention_seconds: int = 0
    failure: str = ""

    @property
    def summary(self) -> str:
        """Return the one line an operator reads about this source."""
        if not self.reachable:
            return f"{self.source} did not answer: {self.failure}"
        if not self.retention_seconds:
            return (
                f"{self.source} answered and declares no retention, so a query longer "
                f"than it keeps will come back short without saying so"
            )
        hours = self.retention_seconds / 3_600
        return f"{self.source} answered; it keeps about {hours:.1f} hours"


@dataclass(frozen=True, slots=True)
class LogQueryBound:
    """What one query was allowed to read."""

    window_seconds: int
    limit: int
    #: What the source said it keeps, or zero when it does not say. Zero is "no
    #: opinion" rather than "keeps nothing": a caller that read it as the latter
    #: would refuse every query against a source that simply does not publish it.
    retention_seconds: int = 0


@dataclass(frozen=True, slots=True)
class LogAnswer:
    """The lines one query returned, and everything that shaped which lines those were."""

    selector: str
    start: datetime
    end: datetime
    lines: tuple[LogLine, ...]
    bound: LogQueryBound
    truncated: bool = False
    #: How much of the requested window the source cannot answer for. Zero when
    #: the source keeps at least the window asked for, or declares no retention.
    retention_shortfall_seconds: int = 0

    @property
    def complete(self) -> bool:
        """Return whether these lines are the whole answer to the question asked."""
        return not self.truncated and not self.retention_shortfall_seconds

    @property
    def summary(self) -> str:
        """Return the sentence that must accompany these lines wherever they are shown."""
        parts = [
            f"{len(self.lines)} line(s) from {self.start:%Y-%m-%d %H:%M} to "
            f"{self.end:%H:%M} matching {self.selector}"
        ]
        if self.truncated:
            parts.append(f"stopped at the bound of {self.bound.limit} lines, so there are more")
        if self.retention_shortfall_seconds:
            parts.append(
                f"the source's retention is {self.retention_shortfall_seconds}s shorter "
                f"than the window asked for, so the earlier part was never available"
            )
        return "; ".join(parts)


@dataclass(frozen=True, slots=True)
class LogReader:
    """One log source, read within bounds it cannot exceed."""

    source: LogSource
    window_seconds: int = DEFAULT_LOG_WINDOW_SECONDS
    limit: int = MAX_LOG_LINES

    def __post_init__(self) -> None:
        if self.window_seconds > MAX_LOG_WINDOW_SECONDS:
            raise BridgeBoundExceeded(
                parameter="log window",
                requested=self.window_seconds,
                limit=MAX_LOG_WINDOW_SECONDS,
                constant="MAX_LOG_WINDOW_SECONDS",
            )
        if self.limit > MAX_LOG_LINES:
            raise BridgeBoundExceeded(
                parameter="log lines per query",
                requested=self.limit,
                limit=MAX_LOG_LINES,
                constant="MAX_LOG_LINES",
            )
        if self.window_seconds <= 0 or self.limit <= 0:
            raise ValueError("A log query with no window or no line budget reads nothing.")

    async def read(self, selector: str, *, at: datetime) -> LogAnswer:
        """Return the lines ``selector`` matches in the window ending at ``at``.

        Raises ``LogSourceUnreachable`` when the source did not answer. An empty
        stream from a healthy Loki and no answer from a dead one lead to opposite
        conclusions about the guest.
        """
        retention = await self.source.retention_seconds()
        shortfall = max(0, self.window_seconds - retention) if retention else 0
        covered = self.window_seconds - shortfall
        start = at - timedelta(seconds=covered)

        # One more than the bound, so "there is more" is something observed
        # rather than inferred from the count happening to equal the limit.
        found = await self.source.lines(
            selector=selector, start=start, end=at, limit=self.limit + 1
        )
        truncated = len(found) > self.limit
        if truncated:
            logger.info("bridge.logs_truncated", selector=selector, limit=self.limit)

        return LogAnswer(
            selector=selector,
            start=start,
            end=at,
            lines=tuple(found[: self.limit]),
            bound=LogQueryBound(
                window_seconds=self.window_seconds,
                limit=self.limit,
                retention_seconds=retention,
            ),
            truncated=truncated,
            retention_shortfall_seconds=shortfall,
        )


async def verify_log_source(source: LogSource, *, name: str = "log source") -> LogVerification:
    """Return what one real call established about ``source``.

    The cheapest question a log system can be asked — what do you keep — which
    is also the one whose answer changes how every later query is reported.
    """
    try:
        retention = await source.retention_seconds()
    except LogSourceUnreachable as unreachable:
        logger.warning("bridge.logs_unreachable", source=name, reason=unreachable.reason)
        return LogVerification(source=name, reachable=False, failure=unreachable.reason)
    except Exception as broken:  # noqa: BLE001 - a transport failure is still a verdict
        # Deliberately broad, for the reason the metrics verification gives: the
        # outcome that must not follow is a clean result nobody actually got.
        logger.warning("bridge.logs_unreachable", source=name, reason=str(broken))
        return LogVerification(
            source=name, reachable=False, failure=f"{type(broken).__name__}: {broken}"
        )
    return LogVerification(source=name, reachable=True, retention_seconds=retention)


__all__ = ["LogAnswer", "LogQueryBound", "LogReader", "LogVerification", "verify_log_source"]
