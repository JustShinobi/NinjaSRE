"""The resolver that narrows a catalogue to one team, reachable without a pipeline state.

``TeamCatalogueResolver`` had exactly three mentions in the repository: an
example in a docstring, a re-export, and an entry in ``__all__``. Nothing ever
built one. The reason is visible in its own signature — it resolves against an
``AgentState``, and the path that serves an investigation holds a request rather
than a state, so the only caller that could use it was the one nobody composed.

So it gains an entry that takes the availability already derived and leaves the
existing one delegating to it. One resolution, two callers. Two implementations
would be two answers to "what can this team run", and the day they drifted a
screen would count one number while an investigation was handed another.
"""

from __future__ import annotations

import pytest

from capabilities.registry.catalogue import Registry, resolve_for
from capabilities.registry.planning import TeamCatalogueResolver
from core.capability.metadata import EvidenceSource, EvidenceType, Requirements, ToolMetadata
from core.capability.ports import ConfiguredIntegrations
from core.capability.registered import build_registration

pytestmark = pytest.mark.unit


def _tool(name: str, *, needs: tuple[str, ...] = ()) -> object:
    return build_registration(
        metadata=ToolMetadata(
            name=name,
            display_name=name,
            description=f"the {name} capability, declared for this test",
            domain="testing",
            evidence_source=EvidenceSource.METRICS,
            evidence_type=EvidenceType.MEASUREMENT,
            requires=Requirements(integrations=needs),
        ),
        call=lambda: None,
        source_module=__name__,
        source_qualname=name,
        input_schema={"type": "object", "properties": {}},
        output_schema={"type": "object", "properties": {}},
    )


def _registry() -> Registry:
    return Registry(
        tools={
            "reads_anything": _tool("reads_anything"),  # type: ignore[dict-item]
            "reads_prometheus": _tool("reads_prometheus", needs=("prometheus",)),  # type: ignore[dict-item]
            "reads_loki": _tool("reads_loki", needs=("loki",)),  # type: ignore[dict-item]
        }
    )


def test_the_stateless_entry_narrows_to_what_the_team_has() -> None:
    resolver = TeamCatalogueResolver(_registry())

    resolved = resolver.for_availability(ConfiguredIntegrations(integrations=("prometheus",)))

    assert {found.name for found in resolved.tools} == {"reads_anything", "reads_prometheus"}


def test_the_exclusion_says_which_integration_would_unlock_it() -> None:
    """An absence and an unconfigured integration look identical without this."""
    resolver = TeamCatalogueResolver(_registry())

    resolved = resolver.for_availability(ConfiguredIntegrations(integrations=("prometheus",)))

    excluded = resolved.exclusion("reads_loki")
    assert excluded is not None
    assert excluded.unmet == ("loki",)


def test_a_team_with_nothing_connected_keeps_only_what_needs_nothing() -> None:
    resolver = TeamCatalogueResolver(_registry())

    resolved = resolver.for_availability(ConfiguredIntegrations())

    assert {found.name for found in resolved.tools} == {"reads_anything"}
    assert {held.name for held in resolved.excluded} == {"reads_prometheus", "reads_loki"}


async def test_the_state_shaped_entry_agrees_with_the_stateless_one() -> None:
    """The property that makes it one resolution rather than two that could drift."""
    from core.domain.alerts.normalisation import RawAlert
    from core.pipeline.state_factory import initial_state
    from core.state.types import TeamContext

    registry = _registry()
    team = TeamContext(node_id="acme/payments", integrations=("prometheus",))
    state = initial_state(RawAlert(payload={"status": "firing"}), team, run_id="run-1")

    with_state = await TeamCatalogueResolver(registry).resolve(state)
    without_state = TeamCatalogueResolver(registry).for_availability(
        ConfiguredIntegrations(integrations=("prometheus",))
    )

    assert [found.name for found in with_state.tools] == [
        found.name for found in without_state.tools
    ]
    assert [held.name for held in with_state.excluded] == [
        held.name for held in without_state.excluded
    ]


def test_both_entries_return_the_same_resolution_for_the_same_availability() -> None:
    """One implementation. The state-shaped entry is a call into the other."""
    registry = _registry()
    availability = ConfiguredIntegrations(integrations=("loki",))

    through_the_resolver = TeamCatalogueResolver(registry).for_availability(availability)
    through_the_catalogue = resolve_for(registry, availability)

    assert [found.name for found in through_the_resolver.tools] == [
        found.name for found in through_the_catalogue.tools
    ]
    assert [held.name for held in through_the_resolver.excluded] == [
        held.name for held in through_the_catalogue.excluded
    ]
