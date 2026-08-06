"""Per-tenant limits on the proxy, from named constants (FR-014).

The proxy is shared, so one tenant's runaway loop is every tenant's latency
unless something stops it. This stops it, and it stops it by *refusing* rather
than queueing.

Queueing is the tempting alternative and it is wrong here. A queue converts a
runaway loop into slow requests for everybody, hides the cause behind a
latency graph, and leaves the loop running. A refusal costs the tenant that
caused it, produces a classified error the agent can act on, and lands in the
audit trail as a thing that happened rather than a thing that was absorbed.

A fixed window rather than a token bucket, because the property an operator
cares about is "no tenant makes more than N calls a minute" and a fixed window
states exactly that. The burst a sliding window would smooth is not a problem
the proxy has: the vendor's own rate limit is the one that bites, and the base
client handles that with backoff where the response says so.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from config.constants.security import (
    CREDENTIAL_PROXY_MAX_REQUESTS_PER_TENANT,
    CREDENTIAL_PROXY_RATE_LIMIT_WINDOW_SECONDS,
)
from platform.credentials.proxy.errors import TenantRateLimited


@dataclass(slots=True)
class _Window:
    """One tenant's count, and when the window it belongs to started."""

    started_at: float
    count: int


@dataclass(slots=True)
class TenantRateLimiter:
    """Counts proxied requests per organisation, in fixed windows.

    ``clock`` is a monotonic source rather than the wall clock. A window keyed
    to wall-clock time is a window that a leap second, an NTP correction, or a
    container's clock skew can widen or reset — and a rate limit that silently
    stops limiting is worse than none, because nobody notices.
    """

    max_requests: int = CREDENTIAL_PROXY_MAX_REQUESTS_PER_TENANT
    window_seconds: float = CREDENTIAL_PROXY_RATE_LIMIT_WINDOW_SECONDS
    clock: Callable[[], float] = time.monotonic
    _windows: dict[str, _Window] = field(default_factory=dict)

    def check(self, org_id: str, *, integration: str = "") -> None:
        """Count one request for ``org_id``, or raise ``TenantRateLimited``.

        Counts *before* deciding, so a refused request still counts. A tenant
        that keeps hammering past its limit does not get a free window by
        virtue of every call failing.
        """
        now = self.clock()
        window = self._windows.get(org_id)
        if window is None or now - window.started_at >= self.window_seconds:
            window = _Window(started_at=now, count=0)
            self._windows[org_id] = window

        window.count += 1
        # The comparison runs on the first request of a window too. A reset path
        # that returned early would make a limit of zero permit one call, which
        # is the shape of bug a limit is supposed to have none of.
        if window.count > self.max_requests:
            raise TenantRateLimited(
                integration,
                org_id=org_id,
                limit=self.max_requests,
                window_seconds=self.window_seconds,
            )

    def snapshot(self) -> Mapping[str, int]:
        """Return each tenant's count in its current window, for health output."""
        now = self.clock()
        return {
            org_id: window.count
            for org_id, window in self._windows.items()
            if now - window.started_at < self.window_seconds
        }

    def reset(self) -> None:
        """Forget every window. For a process that has just taken over serving."""
        self._windows.clear()


__all__ = ["TenantRateLimiter"]
