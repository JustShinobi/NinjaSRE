"""Linking a repeat alert to its investigation rather than discarding it (FR-018).

Fingerprint components: source, normalised target (the components a
normalised alert names), and alert name — the combination the plan's
clarification settles on. Within ``ALERT_DEDUP_WINDOW_SECONDS`` a match is
**linked**, never dropped: the second alert is recorded and attached to the
existing investigation, so an operator who believes it is a distinct incident
can split it. Discarding it would be the one failure mode a deduplication
window cannot be allowed to have.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from config.constants.surfaces import ALERT_DEDUP_WINDOW_SECONDS
from core.domain.alerts.normalisation import NormalisedAlert


def fingerprint(alert: NormalisedAlert, *, team_node_id: str) -> str:
    """Return the deduplication key for ``alert`` within ``team_node_id``."""
    parts = (
        team_node_id,
        alert.alert_source.value,
        alert.alert_name.strip().lower(),
        ",".join(sorted(component.strip().lower() for component in alert.components)),
    )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


@dataclass(slots=True)
class _Entry:
    run_id: str
    recorded_at: float


@dataclass(slots=True)
class DeduplicationIndex:
    """The fingerprint to run-id mapping within the dedup window.

    Held in process memory. The window is minutes, and a restart during it
    produces at worst one duplicate investigation rather than a swallowed
    one — the direction FR-018's clarification chose when it is wrong.
    """

    window_seconds: float = ALERT_DEDUP_WINDOW_SECONDS
    clock: Callable[[], float] = time.monotonic
    _entries: dict[str, _Entry] = field(default_factory=dict)

    def linked_run(self, key: str) -> str | None:
        """Return the run ``key`` is already linked to, or ``None``."""
        entry = self._entries.get(key)
        if entry is None:
            return None
        if self.clock() - entry.recorded_at > self.window_seconds:
            del self._entries[key]
            return None
        return entry.run_id

    def link(self, key: str, run_id: str) -> None:
        """Record that ``key`` now resolves to ``run_id`` for the dedup window."""
        self._entries[key] = _Entry(run_id=run_id, recorded_at=self.clock())


__all__ = ["DeduplicationIndex", "fingerprint"]
