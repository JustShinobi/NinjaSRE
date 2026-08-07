"""Explicit load shedding: what a storm makes ingestion drop is recorded, never silent (FR-020).

A fixed window per source and per team, refusing past the limit rather than
queueing — the same shape as ``gateway/http/rate_limit.py`` and for the same
reason: a queue during an alert storm just delays every alert equally and
hides which ones were never looked at. What is shed is written to ``ShedLog``
so ``routes/health.py`` and ``routes/runs.py`` can answer "what did ingestion
not investigate, and why" (T054).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from config.constants.surfaces import (
    WEBHOOK_MAX_REQUESTS_PER_TEAM,
    WEBHOOK_RATE_LIMIT_WINDOW_SECONDS,
)


def _utc_now() -> datetime:
    """Return the current instant, timezone-aware."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class LoadShedRecord:
    """One inbound alert ingestion did not investigate, and why."""

    source: str
    team_node_id: str
    occurred_at: datetime
    reason: str
    count_in_window: int


@dataclass(slots=True)
class ShedLog:
    """Every shed decision, kept so an operator can answer what was dropped."""

    _records: list[LoadShedRecord] = field(default_factory=list)

    def append(self, record: LoadShedRecord) -> None:
        """Record ``record``."""
        self._records.append(record)

    def most_recent(self, *, source: str = "", team_node_id: str = "") -> LoadShedRecord | None:
        """Return the latest shed matching the given filters, or ``None``."""
        for record in reversed(self._records):
            if source and record.source != source:
                continue
            if team_node_id and record.team_node_id != team_node_id:
                continue
            return record
        return None

    def since(self, moment: datetime) -> tuple[LoadShedRecord, ...]:
        """Return every shed at or after ``moment``, in the order it happened."""
        return tuple(record for record in self._records if record.occurred_at >= moment)

    def all(self) -> tuple[LoadShedRecord, ...]:
        """Return every shed decision this process has recorded."""
        return tuple(self._records)


@dataclass(slots=True)
class _Window:
    started_at: float
    count: int


@dataclass(slots=True)
class LoadShedder:
    """Admits or sheds one inbound webhook, per source and team, per window."""

    max_requests: int = WEBHOOK_MAX_REQUESTS_PER_TEAM
    window_seconds: float = WEBHOOK_RATE_LIMIT_WINDOW_SECONDS
    clock: Callable[[], float] = time.monotonic
    wall_clock: Callable[[], datetime] = _utc_now
    log: ShedLog = field(default_factory=ShedLog)
    _windows: dict[str, _Window] = field(default_factory=dict)

    def admit(self, *, source: str, team_node_id: str) -> bool:
        """Return whether this webhook fits in its source/team window.

        Counts before deciding, so a shed request still counts — a storm past
        the limit does not get a free window because every request after the
        limit is refused.
        """
        key = f"{source}:{team_node_id}"
        now = self.clock()
        window = self._windows.get(key)
        if window is None or now - window.started_at >= self.window_seconds:
            window = _Window(started_at=now, count=0)
            self._windows[key] = window

        window.count += 1
        if window.count > self.max_requests:
            self.log.append(
                LoadShedRecord(
                    source=source,
                    team_node_id=team_node_id,
                    occurred_at=self.wall_clock(),
                    reason=(
                        f"{window.count} requests from {source!r} for team {team_node_id!r} in "
                        f"the last {self.window_seconds:g}s, above the limit of {self.max_requests}"
                    ),
                    count_in_window=window.count,
                )
            )
            return False
        return True


__all__ = ["LoadShedRecord", "LoadShedder", "ShedLog"]
