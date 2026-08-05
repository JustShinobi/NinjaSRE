"""Caching a client per role, without the state that made it dangerous.

Constructing a provider client sets up an SDK client, a connection pool, and a
schema normaliser; doing that per turn is waste. Caching it is fine — and used
to be the source of a race, because an error handler would set a flag on the
shared client ("this provider rejected cache markers") and a concurrent turn
that had *already sent* a request with markers would then take the branch
belonging to the other turn's failure.

The fix is structural rather than a lock. Everything a request depends on is
captured into the request when it is built (see ``core.llm.client._Attempt``),
so a cached client holds no per-turn state for a handler to mutate. What is
cached here is genuinely immutable configuration, and the key spells out every
input to it — because a cache key that omits an input is how one role's client
comes to serve another's requests.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from core.llm.client import ProviderClient
from core.llm.internal.client_cache_key import ClientCacheKey


@dataclass(slots=True)
class ClientCache:
    """A per-key client cache.

    Not thread-safe and not lock-guarded, deliberately: constructing the same
    client twice under a race is harmless — one of them is simply discarded —
    while a lock around every turn's client lookup is contention on the hot
    path for no correctness gain.
    """

    _clients: dict[ClientCacheKey, ProviderClient]

    def __init__(self) -> None:
        self._clients = {}

    def get_or_create(
        self, key: ClientCacheKey, factory: Callable[[], ProviderClient]
    ) -> ProviderClient:
        """Return the cached client for ``key``, building it on first use."""
        existing = self._clients.get(key)
        if existing is not None:
            return existing
        created = factory()
        self._clients[key] = created
        return created

    def invalidate(self, key: ClientCacheKey) -> None:
        """Drop one cached client, for a credential rotation or a config change."""
        self._clients.pop(key, None)

    def clear(self) -> None:
        """Drop every cached client."""
        self._clients.clear()

    def __len__(self) -> int:
        """Return how many clients are cached."""
        return len(self._clients)


__all__ = ["ClientCache"]
