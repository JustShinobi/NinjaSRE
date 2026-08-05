"""The tier-2 half of the pipeline's catalogue and ranking ports.

The investigation pipeline is tier 3 and this package is tier 2, so the
pipeline cannot import the scorer or the resolver — it declares what it needs
and something above both substitutes an implementation. This module is that
implementation, and it is deliberately thin: two adapters and no behaviour of
their own, so the ranking a run got is the ranking ``scoring.rank`` produces
and nothing about the pipeline changed it on the way through.

The composition root wires them::

    resolver = TeamCatalogueResolver(build_registry())
    ranker = CatalogueRanker()

Substituting either is how an ablation is run. Putting the substitution here
rather than inside a stage is what makes "the plan contributed this much" a
measurement rather than an argument.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from capabilities.registry.catalogue import Registry, ResolvedCatalogue, resolve_for
from capabilities.registry.scoring import Incident, rank
from core.capability.metadata import CapabilityMetadata
from core.capability.ports import (
    ConfiguredIntegrations,
    EffectivenessProvider,
    IntegrationAvailability,
    NeutralEffectiveness,
)
from core.pipeline.ports import IncidentSignals, RankedCapability
from core.state.agent_state import AgentState


@dataclass(frozen=True, slots=True)
class CatalogueRanker:
    """Scores a catalogue with the deterministic scorer this package owns.

    ``effectiveness`` is the memory layer's contribution and defaults to the
    neutral provider, which removes the term entirely. That default is also the
    ablation control: a learning mechanism whose contribution cannot be
    switched off cannot be measured.
    """

    effectiveness: EffectivenessProvider = field(default_factory=NeutralEffectiveness)

    def rank(
        self, declarations: Sequence[CapabilityMetadata], signals: IncidentSignals
    ) -> Sequence[RankedCapability]:
        """Return every declaration scored against ``signals``, highest first."""
        scored = rank(
            declarations,
            Incident(
                alert_source=signals.alert_source,
                summary=signals.summary,
                tags=signals.tags,
                domain=signals.domain,
                planned_capabilities=signals.planned_capabilities,
            ),
            effectiveness=self.effectiveness,
        )
        return tuple(
            RankedCapability(name=entry.name, score=entry.score, rationale=entry.rationale)
            for entry in scored
        )


@dataclass(frozen=True, slots=True)
class TeamCatalogueResolver:
    """Resolves the built registry against the integrations a run's team has.

    Availability comes from the team on the state rather than from a captured
    value, so one resolver serves every team in a multi-tenant deployment —
    which is the shape a shared registry and per-team configuration imply.
    """

    registry: Registry

    async def resolve(self, state: AgentState) -> ResolvedCatalogue:
        """Return what the team on ``state`` can run, with the exclusions."""
        return resolve_for(self.registry, self.availability(state))

    def availability(self, state: AgentState) -> IntegrationAvailability:
        """Return what this run's team has configured."""
        return ConfiguredIntegrations(
            integrations=state.team.integrations,
            sandbox_profiles=state.team.sandbox_profiles,
        )


__all__ = [
    "CatalogueRanker",
    "TeamCatalogueResolver",
]
