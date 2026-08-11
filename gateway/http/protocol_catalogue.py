"""Holding a composed bridged catalogue briefly, per team.

Building one means a discovery call per registered server, to infrastructure the
operator runs and this deployment does not. An operator working through a
classification queue refreshes the screen — so without a cache, one person
reading a page becomes up to ``MAX_PROTOCOL_SERVERS_PER_TEAM`` outbound calls
per refresh, aimed at somebody else's systems, from a surface that is only
*reading*.

Three decisions, and the first two are the ones a cache gets wrong.

**Keyed per team, never shared.** A team's registrations are its own. One entry
across teams would show an operator the servers a different team registered,
which is a tenancy leak dressed up as a performance win.

**Expiry is short and absolute.** Thirty seconds, from when the entry was
written, not from when it was last read. An entry refreshed on every read would
keep an outage on the screen for as long as somebody kept looking at it — which
is exactly the period during which they are looking *because* of the outage.

**No negative-result special case.** An unreachable server is cached like any
other answer, for the same short window. Re-probing a down server on every
refresh is how a screen turns one outage into a second one.

The per-server timeout is *not* here: each adapter already applies
``PROTOCOL_DISCOVERY_TIMEOUT_SECONDS`` to its own discovery, and a second
timeout at this layer would be a second thing to disagree with the first about
what "did not answer" means.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from capabilities.protocols.catalogue import BridgedCatalogue
from config.constants.protocols import (
    MAX_CACHED_PROTOCOL_CATALOGUES,
    PROTOCOL_CATALOGUE_CACHE_SECONDS,
)
from platform.persistence.ports.transaction import TenantScope


def _utc_now() -> datetime:
    """Return the current instant, timezone-aware."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class CachedCatalogue:
    """One team's composed catalogue, and when it stops being believed."""

    catalogue: BridgedCatalogue
    written_at: datetime

    def fresh(self, *, now: datetime, ttl_seconds: float) -> bool:
        """Return whether this entry may still be served."""
        return now - self.written_at < timedelta(seconds=ttl_seconds)


@dataclass(slots=True)
class ProtocolCatalogueCache:
    """The bridged catalogues this process is currently willing to reuse."""

    ttl_seconds: float = PROTOCOL_CATALOGUE_CACHE_SECONDS
    capacity: int = MAX_CACHED_PROTOCOL_CATALOGUES
    clock: Callable[[], datetime] = _utc_now
    _entries: OrderedDict[str, CachedCatalogue] = field(default_factory=OrderedDict)

    def key(self, scope: TenantScope) -> str:
        """Return the cache key for ``scope``.

        The organisation *and* the team, because a team identifier is only
        unique inside its organisation and a collision here would serve one
        tenant another's servers.
        """
        return f"{scope.org_id}/{scope.team_node_id or ''}"

    def get(self, scope: TenantScope) -> BridgedCatalogue | None:
        """Return the catalogue held for ``scope``, or ``None`` if it has gone stale."""
        entry = self._entries.get(self.key(scope))
        if entry is None:
            return None
        if not entry.fresh(now=self.clock(), ttl_seconds=self.ttl_seconds):
            del self._entries[self.key(scope)]
            return None
        return entry.catalogue

    def put(self, scope: TenantScope, catalogue: BridgedCatalogue) -> None:
        """Hold ``catalogue`` for ``scope`` until it expires or is evicted."""
        key = self.key(scope)
        self._entries[key] = CachedCatalogue(catalogue=catalogue, written_at=self.clock())
        self._entries.move_to_end(key)
        while len(self._entries) > self.capacity:
            self._entries.popitem(last=False)

    def clear(self) -> None:
        """Forget everything, which is what a configuration change means."""
        self._entries.clear()


__all__ = ["CachedCatalogue", "ProtocolCatalogueCache"]
