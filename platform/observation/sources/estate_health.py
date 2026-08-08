"""The estate's own health, as a signal series a detector can read.

The estate already knows when a resource went unhealthy and when it came back;
this turns that into samples so a detector can say "unhealthy for ten minutes"
rather than "unhealthy right now". Two readings come out of one poll and both
are needed.

**The current state, at the poll instant.** Without it a resource that has been
degraded for a week produces no samples at all, and every window over it is
empty — which an absence detector would read as the estate having gone quiet.

**Every transition since the last poll, at the instant it happened.** Without
these a state change between two polls is invisible, and "it flapped four times
in ten minutes" is unanswerable because only the endpoints were sampled.

The two overlap by construction when a transition lands exactly on the poll
instant, and that costs nothing: the signal key is derived from the name, the
resource, and the instant, so the two readings are one row.

This source makes no provider call. It reads what discovery already wrote, which
is why it is the one source a deployment with no integrations still has.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from config.constants.observation import DEFAULT_TICK_INTERVAL_SECONDS
from platform.observation.sources.port import SignalDeclaration, SignalReading, as_signal
from platform.persistence.ports.estate_repository import EstateQuery, EstateRepository
from platform.persistence.ports.signal_store import Signal, SignalKind

#: The signal every resource in the estate carries. One name, so a detector
#: written against a Proxmox guest also covers a Kubernetes pod.
ESTATE_HEALTH_SIGNAL = "estate.health"

#: What this source is called in a sample's ``source`` field.
ESTATE_SOURCE = "estate"


def declaration(interval_seconds: int = DEFAULT_TICK_INTERVAL_SECONDS) -> SignalDeclaration:
    """Return this source's declaration, at the deployment's tick interval.

    ``rate_limit_per_minute`` is deliberately generous: the "provider" is the
    deployment's own database, and bounding it as though it were a vendor would
    make the one source that costs nothing the one that is polled least.
    """
    return SignalDeclaration(
        source=ESTATE_SOURCE,
        signals=(ESTATE_HEALTH_SIGNAL,),
        interval_seconds=interval_seconds,
        rate_limit_per_minute=600,
        max_provider_calls=0,
    )


@dataclass(frozen=True, slots=True)
class EstateHealthSource:
    """The estate's health transitions, as signals.

    Not a ``SignalReader``: it reads a repository rather than a provider, and
    dressing it as one would mean inventing a provider-call count and a rate
    limit for a database read. It produces the same ``Signal`` records, which is
    what the tick actually needs.
    """

    estate: EstateRepository
    interval_seconds: int = DEFAULT_TICK_INTERVAL_SECONDS

    async def read(
        self,
        *,
        now: datetime,
        since: datetime | None = None,
        query: EstateQuery | None = None,
    ) -> tuple[Signal, ...]:
        """Return one sample per resource at ``now``, plus every transition since ``since``."""
        resources = await self.estate.query(query or EstateQuery(limit=500))
        samples: list[Signal] = []

        for resource in resources:
            samples.append(
                self._sample(
                    resource_id=resource.resource_id,
                    state=resource.reported_health(now).value,
                    observed_at=now,
                    now=now,
                )
            )
            if since is None:
                continue
            for transition in await self.estate.transitions(resource.resource_id):
                if transition.occurred_at < since or transition.occurred_at > now:
                    continue
                samples.append(
                    self._sample(
                        resource_id=resource.resource_id,
                        state=transition.state.value,
                        observed_at=transition.occurred_at,
                        now=now,
                    )
                )

        return tuple(samples)

    def _sample(
        self, *, resource_id: str, state: str, observed_at: datetime, now: datetime
    ) -> Signal:
        """Return one health reading as a stored sample."""
        return as_signal(
            SignalReading(
                name=ESTATE_HEALTH_SIGNAL,
                resource_id=resource_id,
                kind=SignalKind.STATE,
                state=state,
                observed_at=observed_at,
            ),
            source=ESTATE_SOURCE,
            interval_seconds=self.interval_seconds,
            now=now,
        )


__all__ = ["ESTATE_HEALTH_SIGNAL", "ESTATE_SOURCE", "EstateHealthSource", "declaration"]
