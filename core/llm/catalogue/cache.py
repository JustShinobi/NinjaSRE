"""Caching one provider's model listing, per deployment.

Listing is free of tokens, so a screen may call it on every render — but the
vendor call behind it is not free of a round trip, and a deployment is not
improved by three identical calls because three people opened Settings in the
same minute. One cache, per process, keyed by provider: not per team and not
per browser session, because the question "what does this endpoint currently
serve" has one answer for the whole deployment, not one per person asking it.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from config.constants.llm import (
    MODEL_LISTING_CACHE_MAX_ENTRIES,
    MODEL_LISTING_CACHE_TTL_SECONDS,
)
from core.llm.catalogue import ModelOffering


@dataclass(frozen=True, slots=True)
class _Entry:
    models: tuple[ModelOffering, ...]
    fetched_at: float


@dataclass(slots=True)
class ModelCatalogueCache:
    """A deployment-wide, in-process cache of what each provider currently lists.

    ``clock`` is injected so a test can move time forward without sleeping —
    the same reason the retry policy elsewhere in this package takes one.
    """

    ttl_seconds: float = MODEL_LISTING_CACHE_TTL_SECONDS
    max_entries: int = MODEL_LISTING_CACHE_MAX_ENTRIES
    clock: Callable[[], float] = field(default=time.monotonic)
    _entries: dict[str, _Entry] = field(default_factory=dict)
    #: Insertion order, oldest first — used only to evict when the cache is
    #: over its declared cap, never to decide freshness.
    _order: list[str] = field(default_factory=list)

    async def get(
        self,
        provider_id: str,
        *,
        fetch: Callable[[], Awaitable[tuple[ModelOffering, ...]]],
        refresh: bool = False,
    ) -> tuple[ModelOffering, ...]:
        """Return ``provider_id``'s cached listing, fetching it when there is none fresh enough.

        ``refresh=True`` ignores whatever is cached and calls ``fetch`` again,
        which is what an operator's own "Reload models" asks for.
        """
        now = self.clock()
        if not refresh:
            cached = self._entries.get(provider_id)
            if cached is not None and now - cached.fetched_at <= self.ttl_seconds:
                return cached.models

        models = await fetch()
        self._store(provider_id, models, now)
        return models

    def _store(self, provider_id: str, models: tuple[ModelOffering, ...], now: float) -> None:
        if provider_id in self._entries:
            self._order.remove(provider_id)
        self._entries[provider_id] = _Entry(models=models, fetched_at=now)
        self._order.append(provider_id)
        while len(self._order) > self.max_entries:
            oldest = self._order.pop(0)
            self._entries.pop(oldest, None)

    def clear(self) -> None:
        """Forget every cached entry.

        For a test that registers a second, different implementation for a
        provider already cached within this same process — the shipped
        equivalent of ``core.llm.factory.reset_factory`` — and, in a running
        deployment, for the same reason that one exists: a configuration
        reload should not keep serving what the previous configuration cached.
        """
        self._entries.clear()
        self._order.clear()


__all__ = ["ModelCatalogueCache"]
