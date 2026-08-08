"""Turning what a provider said into a state that can be compared across providers.

A provider status string copied into a column is not health. It cannot be
compared — ``running`` and ``ACTIVE`` and ``up`` are one state spelled three
ways — it changes meaning when the provider changes, and it cannot be explained
to an operator who has never used that provider.

So every source declares a mapping: provider status to a member of the closed
set, and the raw string is kept beside the verdict. Both halves are load-bearing.
The verdict is what makes "how many things are unhealthy" answerable; the raw
value is what makes a *wrong* mapping diagnosable, because the only way to see
that ``suspended`` was mapped to unhealthy when it should have been maintenance
is to still have the word ``suspended``.

**An unmapped status is ``UNKNOWN``, never ``HEALTHY``.** This is the rule that
costs the most and is worth the most. A provider that adds a status nobody has
mapped yet — a new lifecycle state, a new error class — would otherwise be
reported as fine, and an estate that reports a state it has never seen as fine
is an estate that will one day report a fire as fine. ``UNKNOWN`` says what is
true: we looked, and we cannot say.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from platform.persistence.ports.estate_repository import ResourceHealth

#: The statuses nearly every provider uses, mapped once so that an integration
#: declaring nothing still gets sensible answers for the words everyone shares.
#: Lower-cased keys; lookup folds the provider's own casing, because ``ACTIVE``
#: and ``active`` are not two states and a mapping that treated them as two
#: would report half an estate as unknown.
COMMON_STATUSES: Mapping[str, ResourceHealth] = {
    "running": ResourceHealth.HEALTHY,
    "online": ResourceHealth.HEALTHY,
    "active": ResourceHealth.HEALTHY,
    "available": ResourceHealth.HEALTHY,
    "ok": ResourceHealth.HEALTHY,
    "up": ResourceHealth.HEALTHY,
    "ready": ResourceHealth.HEALTHY,
    "healthy": ResourceHealth.HEALTHY,
    "degraded": ResourceHealth.DEGRADED,
    "warning": ResourceHealth.DEGRADED,
    "partial": ResourceHealth.DEGRADED,
    "stopped": ResourceHealth.UNHEALTHY,
    "offline": ResourceHealth.UNHEALTHY,
    "failed": ResourceHealth.UNHEALTHY,
    "error": ResourceHealth.UNHEALTHY,
    "down": ResourceHealth.UNHEALTHY,
    "unhealthy": ResourceHealth.UNHEALTHY,
    "crashed": ResourceHealth.UNHEALTHY,
    # A guest somebody paused is not a fault, and it is not healthy either. It
    # is the case maintenance exists for, and mapping it to unhealthy is how an
    # operator learns to ignore the problem count.
    "maintenance": ResourceHealth.MAINTENANCE,
    "paused": ResourceHealth.MAINTENANCE,
    "suspended": ResourceHealth.MAINTENANCE,
    "unknown": ResourceHealth.UNKNOWN,
}


@dataclass(frozen=True, slots=True)
class StatusMapping:
    """One source's declared translation from its own vocabulary into the closed set.

    ``overrides`` come first and ``COMMON_STATUSES`` second, so a provider for
    which ``active`` genuinely means something else can say so without the
    shared table having to grow a special case per vendor.
    """

    source: str = ""
    overrides: Mapping[str, ResourceHealth] = field(default_factory=dict)

    def state_for(self, raw_status: str) -> ResourceHealth:
        """Return the state ``raw_status`` maps to, or ``UNKNOWN``.

        Never ``HEALTHY`` for a status nobody mapped. A provider that adds a
        lifecycle state we have not seen must not be reported as fine because
        of it.
        """
        folded = raw_status.strip().lower()
        if not folded:
            return ResourceHealth.UNKNOWN
        override = self.overrides.get(folded)
        if override is not None:
            return override
        return COMMON_STATUSES.get(folded, ResourceHealth.UNKNOWN)

    def knows(self, raw_status: str) -> bool:
        """Return whether ``raw_status`` was mapped rather than defaulted.

        The difference between "we mapped this to unknown on purpose" and "we
        have never seen this word", which is what an operator needs to decide
        whether to add a mapping.
        """
        folded = raw_status.strip().lower()
        return folded in self.overrides or folded in COMMON_STATUSES

    def with_overrides(self, overrides: Mapping[str, ResourceHealth]) -> StatusMapping:
        """Return this mapping with ``overrides`` merged over its own."""
        return StatusMapping(source=self.source, overrides={**self.overrides, **overrides})


#: What a source that declared nothing gets. Not empty: the shared vocabulary is
#: still applied, so an integration that maps nothing still reports a stopped
#: guest as unhealthy rather than as unknown.
DEFAULT_MAPPING = StatusMapping()


__all__ = ["COMMON_STATUSES", "DEFAULT_MAPPING", "StatusMapping"]
