"""Probes, kept until the model underneath them changes.

A probe costs a dozen small calls. Retaking it on every process start would make
the suite the thing an operator notices about starting the platform, so results
are cached — and the interesting half of a cache is the invalidation.

The key is the provider and the model. The *identity* also carries a
fingerprint, and a lookup whose fingerprint disagrees with the stored one is a
miss that also evicts: a model pulled again underneath a running deployment is a
different model with the same name, and answering from the old measurement is
how a deployment ends up sending forty schemas to a build that can hold eight.

Bounded and least-recently-used, because an endpoint serving thirty models
should not be able to grow this without limit.
"""

from __future__ import annotations

from collections import OrderedDict

from config.constants.llm import MODEL_PROBE_CACHE_MAX_ENTRIES
from core.llm.probe.report import ModelIdentity, ModelProbe


class ProbeCache:
    """Probe results by model, invalidated when the model changes."""

    def __init__(self, *, max_entries: int = MODEL_PROBE_CACHE_MAX_ENTRIES) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self._max_entries = max_entries
        self._entries: OrderedDict[tuple[str, str], ModelProbe] = OrderedDict()

    def get(self, identity: ModelIdentity) -> ModelProbe | None:
        """Return the stored probe for ``identity``, or ``None``.

        A stored probe whose fingerprint differs from ``identity``'s is dropped
        rather than returned. Dropping rather than merely declining is what makes
        a changed model cost one re-probe instead of one per lookup.
        """
        stored = self._entries.get(identity.slot)
        if stored is None:
            return None
        if stored.identity.fingerprint != identity.fingerprint:
            del self._entries[identity.slot]
            return None
        self._entries.move_to_end(identity.slot)
        return stored

    def put(self, probe: ModelProbe) -> None:
        """Store ``probe``, evicting the least recently used entry if full."""
        self._entries[probe.identity.slot] = probe
        self._entries.move_to_end(probe.identity.slot)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def invalidate(self, identity: ModelIdentity) -> None:
        """Drop whatever is stored for ``identity``'s model."""
        self._entries.pop(identity.slot, None)

    def clear(self) -> None:
        """Drop every stored probe."""
        self._entries.clear()

    def __len__(self) -> int:
        """Return how many probes are held."""
        return len(self._entries)


__all__ = ["ProbeCache"]
