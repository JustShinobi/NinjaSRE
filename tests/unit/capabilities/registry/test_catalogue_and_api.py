"""The built catalogue, and what a reader is shown of it.

Two things are asserted here that nothing else covers. The registry is only
obtainable by passing validation, so there is no route to a catalogue that has
not been checked. And the read API tells an operator not just what exists, but
what *they* can run and what is missing if they cannot — the distinction
between "not written" and "not configured" is the one an operator can act on.

The repository's own catalogue is exercised too. Every other test here builds a
fixture; this is the one that would notice a shipped skill directing a tool
somebody renamed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from capabilities.registry.api import (
    as_records,
    catalogue_view,
    find,
    resolved_view,
    summary,
)
from capabilities.registry.catalogue import (
    Registry,
    build_registry,
    registry_from,
    reset_registry_cache,
    resolve_for,
)
from capabilities.registry.discovery import DiscoveredCatalogue
from capabilities.registry.validation import ValidationError
from config.constants.capabilities import (
    MAX_CATALOGUE_METADATA_TOKENS,
    MAX_SKILL_METADATA_TOKENS,
)
from core.capability.metadata import (
    CapabilityKind,
    EvidenceType,
    Requirements,
    SideEffectLevel,
    ToolMetadata,
)
from core.capability.ports import ConfiguredIntegrations
from core.capability.registered import RegisteredTool

pytestmark = pytest.mark.unit


def _tool(name: str, *, requires: Requirements = Requirements()) -> RegisteredTool:
    return RegisteredTool(
        metadata=ToolMetadata(
            name=name,
            display_name=name.replace("_", " "),
            description="Reads something and reports what it read.",
            domain="observability",
            tags=("logs",),
            use_cases=("find the failing endpoint",),
            anti_examples=("a billing question",),
            requires=requires,
            evidence_source="datadog",
            evidence_type=EvidenceType.LOG,
            side_effect_level=SideEffectLevel.READ,
            parallel_safe=True,
        ),
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        output_schema={"type": "object", "properties": {}},
        call=lambda: None,
        source_module="capabilities.tools.example",
        source_qualname=name,
    )


# --- Building -----------------------------------------------------------------


def test_a_registry_is_only_obtainable_by_passing_validation(tmp_path: Path) -> None:
    """There is no window in which a caller holds an unchecked catalogue."""
    reset_registry_cache()
    directory = tmp_path / "dangling"
    directory.mkdir()
    (directory / "SKILL.md").write_text(
        "---\n"
        "name: dangling\n"
        "description: Directs a tool nobody declared.\n"
        "domain: observability\n"
        "directs_tools: [no_such_tool]\n"
        "---\n\nBody.\n",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="dangling-directed-tool"):
        build_registry(tool_packages=(), skill_roots=(tmp_path,), use_cache=False)


def test_the_unvalidated_constructor_is_not_the_one_callers_reach_for() -> None:
    """``registry_from`` builds without checking, which is why it is not the door.

    It exists so validation and construction are separable in tests. Reaching
    for it in production code is how a broken catalogue gets past the gate, and
    the naming is the only thing stopping that — so it is worth a test saying so.
    """
    broken = DiscoveredCatalogue(tools=(_tool("t"), _tool("t")))

    assert len(registry_from(broken).tools) == 1


def test_the_registry_is_cached_because_building_it_imports_the_repository() -> None:
    reset_registry_cache()

    first = build_registry()
    second = build_registry()

    assert first is second


def test_resetting_the_cache_rebuilds() -> None:
    first = build_registry()
    reset_registry_cache()

    assert build_registry() is not first


def test_the_repository_catalogue_builds_and_validates() -> None:
    """The test that notices a shipped skill directing a renamed tool."""
    reset_registry_cache()

    registry = build_registry()

    assert registry.tools
    assert registry.skills


def test_every_shipped_skill_is_inside_the_per_skill_budget() -> None:
    """FR-007, against the skills that actually ship rather than a fixture."""
    reset_registry_cache()
    registry = build_registry()

    oversized = {
        name: skill.metadata_tokens
        for name, skill in registry.skills.items()
        if skill.metadata_tokens > MAX_SKILL_METADATA_TOKENS
    }

    assert oversized == {}


def test_the_shipped_skill_index_is_inside_the_catalogue_budget() -> None:
    """SC-002, measured rather than estimated."""
    reset_registry_cache()
    registry = build_registry()

    total = sum(skill.metadata_tokens for skill in registry.skills.values())

    assert total <= MAX_CATALOGUE_METADATA_TOKENS


def test_no_shipped_skill_instructs_shell_execution() -> None:
    """Asserted through the build, which is where it has to hold."""
    reset_registry_cache()

    assert build_registry().skills


def test_every_shipped_write_tool_carries_approval_and_a_rollback_plan() -> None:
    reset_registry_cache()
    registry = build_registry()

    for name, found in registry.tools.items():
        metadata = found.metadata
        if metadata.side_effect_level.needs_approval:
            assert metadata.requires_approval, name
            assert metadata.approval_reason.strip(), name
            assert metadata.rollback_plan or metadata.rollback_planner, name


def test_a_shipped_rollback_planner_names_the_specific_action() -> None:
    """ "Scale it back" is not a plan. The workload and environment have to be in it."""
    reset_registry_cache()
    registry = build_registry()

    scale = registry.tool("scale_workload")
    assert scale is not None
    planner = scale.metadata.rollback_planner
    assert planner is not None

    plan = planner.plan({"workload": "checkout-api", "environment": "production", "replicas": 12})

    assert "checkout-api" in plan.summary
    assert "production" in plan.summary
    assert plan.steps


def test_a_restart_says_it_cannot_be_undone() -> None:
    """The one shipped action whose plan has to admit it is not reversible."""
    reset_registry_cache()
    registry = build_registry()

    restart = registry.tool("restart_workload")
    assert restart is not None
    planner = restart.metadata.rollback_planner
    assert planner is not None

    plan = planner.plan({"workload": "checkout-api", "environment": "production"})

    assert not plan.reversible


# --- The read API --------------------------------------------------------------


def test_the_catalogue_view_covers_both_kinds() -> None:
    reset_registry_cache()
    views = catalogue_view(build_registry())

    kinds = {view.kind for view in views}
    assert kinds == {CapabilityKind.TOOL, CapabilityKind.SKILL}


def test_a_view_without_availability_reads_as_everything_available() -> None:
    """Generated documentation describes what ships, not one deployment."""
    registry = Registry(
        tools={
            "needs_splunk": _tool("needs_splunk", requires=Requirements(integrations=("splunk",)))
        }
    )

    view = find(catalogue_view(registry), "needs_splunk")

    assert view is not None
    assert view.available


def test_a_view_with_availability_says_what_is_missing() -> None:
    registry = Registry(
        tools={
            "needs_splunk": _tool("needs_splunk", requires=Requirements(integrations=("splunk",)))
        }
    )

    view = find(catalogue_view(registry, ConfiguredIntegrations(integrations=())), "needs_splunk")

    assert view is not None
    assert not view.available
    assert view.unmet == ("splunk",)


def test_a_resolved_view_agrees_with_the_resolution_it_came_from() -> None:
    registry = Registry(
        tools={
            "available": _tool("available"),
            "unavailable": _tool("unavailable", requires=Requirements(integrations=("splunk",))),
        }
    )
    catalogue = resolve_for(registry, ConfiguredIntegrations(integrations=()))

    views = resolved_view(registry, catalogue)

    assert {view.name for view in views if view.available} == {"available"}


def test_a_tool_view_carries_the_schema_the_model_would_be_given() -> None:
    registry = Registry(tools={"reads": _tool("reads")})

    view = find(catalogue_view(registry), "reads")

    assert view is not None
    assert view.input_schema is not None
    assert "query" in view.input_schema["properties"]


def test_the_records_survive_json() -> None:
    """The console reads these over a wire, so anything unserialisable is lost."""
    reset_registry_cache()
    records = as_records(catalogue_view(build_registry()))

    assert json.loads(json.dumps(records)) == records


def test_the_summary_counts_what_a_catalogue_page_leads_with() -> None:
    reset_registry_cache()
    views = catalogue_view(build_registry())

    counts = summary(views)

    assert counts["tools"] + counts["skills"] == len(views)
    assert counts["available"] + counts["excluded"] == len(views)
    assert counts["approval_gated"] >= 1
