"""In-memory observation history, keyed the way a real one is.

The dictionary is keyed by ``signal_id`` rather than appended to, which is the
whole of idempotence: a poller that retried overwrites its own sample instead of
adding a second one that would move an average nobody could see move.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from platform.persistence.fakes.state import TenantState
from platform.persistence.ports.signal_store import (
    Signal,
    SignalQuery,
    check_signal_limit,
    matches,
)


@dataclass(slots=True)
class FakeSignalStore:
    """One organisation's signals."""

    org_id: str
    state: TenantState

    async def append(self, signals: Sequence[Signal]) -> tuple[Signal, ...]:
        """Store ``signals`` and return them, replacing any with the same key."""
        for signal in signals:
            self.state.signals[signal.signal_id] = signal
        return tuple(signals)

    async def window(self, query: SignalQuery) -> tuple[Signal, ...]:
        """Return the samples matching ``query``, oldest first."""
        limit = check_signal_limit(query.limit)
        found = [signal for signal in self.state.signals.values() if matches(signal, query)]
        found.sort(key=lambda signal: (signal.observed_at, signal.signal_id))
        return tuple(found[:limit])

    async def latest(
        self,
        *,
        names: tuple[str, ...] = (),
        resource_ids: tuple[str, ...] = (),
    ) -> tuple[Signal, ...]:
        """Return the newest sample per ``(name, resource)``, however old it is."""
        newest: dict[tuple[str, str], Signal] = {}
        for signal in self.state.signals.values():
            if names and signal.name not in names:
                continue
            if resource_ids and signal.resource_id not in resource_ids:
                continue
            key = (signal.name, signal.resource_id)
            held = newest.get(key)
            if held is None or signal.observed_at > held.observed_at:
                newest[key] = signal
        return tuple(sorted(newest.values(), key=lambda signal: signal.signal_id))

    async def prune(self, *, before: datetime) -> int:
        """Delete samples observed before ``before`` and return how many went."""
        stale = [key for key, signal in self.state.signals.items() if signal.observed_at < before]
        for key in stale:
            del self.state.signals[key]
        return len(stale)


__all__ = ["FakeSignalStore"]
