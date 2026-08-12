"""One observation tick: poll every composed source, store what they answered.

``Poller`` rations one source — an interval, a call budget, a reading cap — and
has no opinion about which resources to ask about or where the answers go. This
is the piece around it, and the reason it exists as a runner rather than a loop
inside the dispatcher is two properties that are easy to lose:

**The resources are read fresh each tick.** A guest the last estate sweep
discovered has to be polled by this one. A map built once at composition would
be one sweep behind for ever, and the resource nobody could explain the silence
of would be the newest one.

**A source that fails does not take the tick with it.** One metrics system
having an afternoon must not cost every other signal in the deployment. The
failure is logged with the source named, because a signal that stops arriving
is otherwise indistinguishable from a resource that went quiet — and only one
of those is an incident.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from platform.observability.logging import get_logger
from platform.observation.sources.poller import Poller
from platform.observation.sources.port import SignalReader
from platform.persistence.ports.signal_store import Signal

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SignalWriter:
    """What a tick needs of a signal store, and nothing else."""

    async def append(self, signals: Sequence[Signal]) -> tuple[Signal, ...]:
        """Store ``signals`` and return them as stored."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class ObservationTickRunner:
    """Polls every composed source once, and stores what came back."""

    sources: tuple[SignalReader, ...] = ()
    #: Which resources to ask about, called once per tick. A callable rather
    #: than a list, because the estate changes underneath this and the whole
    #: point is to ask about what exists now.
    resources: Callable[[], tuple[str, ...]] = tuple
    store: SignalWriter | None = None

    async def tick(self, *, now: datetime) -> int:
        """Poll every source and return how many signals were stored."""
        if not self.sources:
            return 0

        resource_ids = tuple(self.resources())
        if not resource_ids:
            # A poll over no resources is a provider call that cannot answer.
            return 0

        stored = 0
        for reader in self.sources:
            name = reader.declaration.source
            try:
                signals = await Poller(reader=reader).poll(resource_ids=resource_ids, now=now)
            except Exception as failed:  # noqa: BLE001 — one source must not end the tick
                logger.warning("observation.source_failed", source=name, error=str(failed))
                continue
            if not signals or self.store is None:
                continue
            written = await self.store.append(signals)
            stored += len(written)
            logger.info("observation.polled", source=name, signals=len(written))

        return stored


__all__ = ["ObservationTickRunner", "SignalWriter"]
