"""The scheduled job that fills the estate's signals.

``ObservationTickRunner`` polls the sources and stores what they say; this is
what a claimed ``observation.tick`` job runs, and the piece that knows where the
resources and the sources come from.

**The guests map is built here.** It needs two things that live apart: the
estate's resources, which change with every sweep, and the exporter's spelling
of one guest, which the integration owns. ``platform/`` may not import an
integration and an integration may not read the estate, so the join belongs at
the composition layer — which is this one.

**It is rebuilt every tick.** A guest the last sweep discovered has to be polled
by this one, and a map built once would be one sweep behind for ever.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from gateway.http.state import GatewayState
from integrations.prometheus.pressure_source import PressureSignalSource, guest_id_for
from platform.observability.logging import get_logger
from platform.observation.tick import ObservationTickRunner
from platform.persistence.ports.estate_repository import EstateQuery
from platform.scheduler.dispatch import JobContext

logger = get_logger(__name__)


def guests_of(resources: Sequence[Any]) -> dict[str, str]:
    """Return the exporter identifier for each resource that has one.

    A resource with no usable identifier is left out rather than given a guess:
    a matcher built from an empty identity answers for every guest on the
    cluster, and the number that comes back belongs to somebody else.
    """
    mapped: dict[str, str] = {}
    for resource in resources:
        attributes: Mapping[str, Any] = getattr(resource, "attributes", {}) or {}
        try:
            vmid = int(attributes.get("vmid", 0) or 0)
        except (TypeError, ValueError):
            # An attribute an integration wrote is not a schema this can rely on.
            continue
        guest = guest_id_for(str(getattr(resource, "kind", "")), vmid=vmid)
        if guest:
            mapped[str(resource.resource_id)] = guest
    return mapped


@dataclass(frozen=True, slots=True)
class ObservationTickJobRunner:
    """Reads the estate, polls what watches it, and stores the readings."""

    state: GatewayState

    async def run(self, context: JobContext) -> Mapping[str, Any]:
        """Poll every composed source about the estate as it stands now."""
        async with self.state.gateway.begin(context.scope) as uow:
            resources = await uow.estate.query(EstateQuery())
            guests = guests_of(resources)
            if not guests:
                logger.info("observation.tick_skipped", reason="no guest carries an identifier")
                return {"polled": 0, "stored": 0, "resources": len(resources)}

            sources = tuple(
                PressureSignalSource(client=client, guests=guests)
                for client in self.state.signal_sources
            )
            stored = await ObservationTickRunner(
                sources=sources,
                resources=lambda: tuple(guests),
                store=uow.signals,
            ).tick(now=context.fire_time)

        return {"polled": len(guests), "stored": stored, "resources": len(resources)}


__all__ = ["ObservationTickJobRunner", "guests_of"]
