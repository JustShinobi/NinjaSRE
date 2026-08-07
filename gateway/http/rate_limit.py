"""Per-principal and per-team limits on the REST API, from named constants (FR-007).

Two fixed windows rather than one: a single caller hammering the API must not
be able to spend a whole team's share before any of that team's other tokens
get a turn, and a team with many callers must still have an aggregate ceiling.
Refused rather than queued, for the same reason the credential proxy refuses —
a queue turns a runaway caller into slow responses for everybody and hides the
cause behind a latency graph.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from config.constants.surfaces import (
    API_MAX_REQUESTS_PER_PRINCIPAL,
    API_MAX_REQUESTS_PER_TEAM,
    API_RATE_LIMIT_WINDOW_SECONDS,
)
from gateway.http.errors import ApiProblem


class ApiRateLimited(ApiProblem):
    """A principal or a team has spent its share of the API for this window."""

    def __init__(self, *, scope: str, key: str, limit: int, window_seconds: float) -> None:
        super().__init__(
            status_code=429,
            error_type="rate_limited",
            message=(
                f"{scope} {key!r} has made {limit} requests in the last "
                f"{window_seconds:g}s, which is its limit. The request is refused rather "
                f"than queued."
            ),
        )
        self.scope = scope
        self.key = key
        self.limit = limit
        self.window_seconds = window_seconds


@dataclass(slots=True)
class _Window:
    started_at: float
    count: int


@dataclass(slots=True)
class FixedWindowLimiter:
    """Counts requests per key, in fixed windows, refusing past the limit."""

    max_requests: int
    window_seconds: float
    scope: str
    clock: Callable[[], float] = time.monotonic
    _windows: dict[str, _Window] = field(default_factory=dict)

    def check(self, key: str) -> None:
        """Count one request for ``key``, or raise ``ApiRateLimited``.

        Counts before deciding, so a refused request still counts — a caller
        past its limit does not get a free window because every call fails.
        """
        now = self.clock()
        window = self._windows.get(key)
        if window is None or now - window.started_at >= self.window_seconds:
            window = _Window(started_at=now, count=0)
            self._windows[key] = window

        window.count += 1
        if window.count > self.max_requests:
            raise ApiRateLimited(
                scope=self.scope,
                key=key,
                limit=self.max_requests,
                window_seconds=self.window_seconds,
            )

    def snapshot(self) -> Mapping[str, int]:
        """Return each key's count in its current window, for health output."""
        now = self.clock()
        return {
            key: window.count
            for key, window in self._windows.items()
            if now - window.started_at < self.window_seconds
        }

    def reset(self) -> None:
        """Forget every window."""
        self._windows.clear()


@dataclass(slots=True)
class ApiRateLimiter:
    """The two windows a request is checked against, principal then team."""

    principal: FixedWindowLimiter = field(
        default_factory=lambda: FixedWindowLimiter(
            max_requests=API_MAX_REQUESTS_PER_PRINCIPAL,
            window_seconds=API_RATE_LIMIT_WINDOW_SECONDS,
            scope="principal",
        )
    )
    team: FixedWindowLimiter = field(
        default_factory=lambda: FixedWindowLimiter(
            max_requests=API_MAX_REQUESTS_PER_TEAM,
            window_seconds=API_RATE_LIMIT_WINDOW_SECONDS,
            scope="team",
        )
    )

    def check(self, *, principal_id: str, team_node_id: str | None) -> None:
        """Raise ``ApiRateLimited`` if either window is spent for this request."""
        self.principal.check(principal_id)
        if team_node_id:
            self.team.check(team_node_id)


__all__ = ["ApiRateLimited", "ApiRateLimiter", "FixedWindowLimiter"]
