"""What this team can actually run, and what to say when the answer is nothing.

The stage itself is thin — it asks the resolver and writes the answer down. The
part worth the module is the second half: an investigation that cannot execute
a single capability must end with something an operator can act on.

"No integrations configured" is not that. It is true, and it leaves the person
reading it exactly where they started. What they need is which integration to
connect, how many capabilities it would unlock, and which of those would have
been used for the alert that just fired — three facts the exclusion records
already contain and that nothing else in the system is going to assemble.

The alert source is detected here without a model call. It is a property of the
payload's shape, intake has not run yet, and spending a model call to say
"cannot investigate" would be spending the run's only cost on its cheapest
sentence.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from config.prompts.investigation import (
    NO_INTEGRATIONS_DETAIL,
    NO_INTEGRATIONS_HEADLINE,
    NO_INTEGRATIONS_STEP,
    NO_INTEGRATIONS_UNKNOWN_STEP,
)
from core.domain.alerts.normalisation import detect_source
from core.pipeline.ports import NO_CATALOGUE, CatalogueResolver, FixedCatalogueResolver
from core.state.agent_state import AgentState, StateUpdates
from core.state.catalogue import ResolvedCapabilities
from core.state.types import InvestigationOutcome, OutcomeKind, StageName

#: How many blocked capabilities are named per suggested integration. Enough to
#: show what connecting it buys, few enough that the outcome stays readable.
MAX_NAMED_CAPABILITIES = 3

#: How many integrations the outcome suggests connecting. An operator acts on
#: the first one or two; a list of eleven is a list nobody reads.
MAX_SUGGESTED_INTEGRATIONS = 3


@dataclass(frozen=True, slots=True)
class ResolveIntegrationsStage:
    """Determine the team's catalogue, and end the run usefully when it is empty."""

    resolver: CatalogueResolver = FixedCatalogueResolver(NO_CATALOGUE)

    @property
    def name(self) -> StageName:
        """Return which of the six stages this is."""
        return StageName.RESOLVE_INTEGRATIONS

    async def __call__(self, state: AgentState) -> StateUpdates:
        """Return the resolved catalogue, with an actionable outcome when it is empty."""
        catalogue = await self.resolver.resolve(state)
        resolved = ResolvedCapabilities.of(
            catalogue.tools, catalogue.metadata(), catalogue.excluded
        )
        investigation = replace(state.investigation, catalogue=resolved)

        if resolved:
            return StateUpdates(investigation=investigation)

        return StateUpdates(
            investigation=replace(investigation, outcome=zero_integration_outcome(resolved, state))
        )


def zero_integration_outcome(
    resolved: ResolvedCapabilities, state: AgentState
) -> InvestigationOutcome:
    """Return the outcome a team with nothing configured gets.

    Specific, and specific to *this* alert: the integration whose name matches
    the source that fired is suggested first, because that is the one whose
    capabilities were written for the payload sitting in front of the operator.
    """
    source = detect_source(state.raw)
    missing = _ordered_by_relevance(resolved, source.value)

    steps = [
        NO_INTEGRATIONS_STEP.format(
            integration=integration,
            count=len(resolved.blocked_by(integration)),
            examples=", ".join(resolved.blocked_by(integration)[:MAX_NAMED_CAPABILITIES]),
        )
        for integration in missing[:MAX_SUGGESTED_INTEGRATIONS]
    ]

    return InvestigationOutcome(
        kind=OutcomeKind.NO_INTEGRATIONS,
        headline=NO_INTEGRATIONS_HEADLINE,
        detail=NO_INTEGRATIONS_DETAIL.format(
            source=source.value, excluded_count=len(resolved.excluded)
        ),
        next_steps=tuple(steps) if steps else (NO_INTEGRATIONS_UNKNOWN_STEP,),
    )


def _ordered_by_relevance(resolved: ResolvedCapabilities, alert_source: str) -> tuple[str, ...]:
    """Return the missing integrations, the ones matching ``alert_source`` first.

    Matching is on the name containing the source, or the source containing the
    name: an ``alertmanager`` alert is served by a ``prometheus`` integration
    under one deployment's naming and by ``alertmanager`` under another's, and
    the ordering should survive both.
    """
    missing = resolved.missing_integrations()
    wanted = alert_source.strip().lower()

    def relevance(integration: str) -> int:
        name = integration.strip().lower()
        return 0 if wanted and (wanted in name or name in wanted) else 1

    return tuple(sorted(missing, key=lambda name: (relevance(name), missing.index(name))))


__all__ = [
    "MAX_NAMED_CAPABILITIES",
    "MAX_SUGGESTED_INTEGRATIONS",
    "ResolveIntegrationsStage",
    "zero_integration_outcome",
]
