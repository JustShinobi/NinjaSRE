"""Resolution, scoring, and the bounded set one turn actually carries.

Three properties are load-bearing here and each has a success criterion behind
it: the cap holds at catalogue scale (SC-001), the reserve is never crowded out
(FR-014), and the same incident against the same catalogue produces the same
selection every time (SC-005). The last one is the quiet one — nothing fails
when it breaks, the evaluation suite just stops being able to attribute a
regression to anything.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from capabilities.registry.catalogue import Registry, ResolvedCatalogue, resolve_for
from capabilities.registry.disclosure import DiscoveredSkill, load_skill
from capabilities.registry.scoring import Incident, rank, score_capability
from capabilities.registry.selection import (
    SelectionError,
    select,
    selection_record,
)
from config.constants.capabilities import SECONDARY_EVIDENCE_SOURCES
from config.constants.investigation import (
    MAX_AGENT_TOOL_SCHEMAS,
    MAX_SECONDARY_FALLBACK_TOOLS,
)
from core.capability.metadata import (
    AppliesWhen,
    EvidenceSource,
    EvidenceType,
    Requirements,
    SideEffectLevel,
    SkillMetadata,
    ToolMetadata,
)
from core.capability.ports import ConfiguredIntegrations
from core.capability.registered import RegisteredTool

pytestmark = pytest.mark.unit


def _tool(
    name: str,
    *,
    source: str = "datadog",
    tags: tuple[str, ...] = (),
    use_cases: tuple[str, ...] = (),
    anti_examples: tuple[str, ...] = (),
    domain: str = "",
    requires: Requirements = Requirements(),
) -> RegisteredTool:
    return RegisteredTool(
        metadata=ToolMetadata(
            name=name,
            display_name=name,
            description="Reads something and reports what it read.",
            domain=domain,
            tags=tags,
            use_cases=use_cases,
            anti_examples=anti_examples,
            requires=requires,
            evidence_source=source,
            evidence_type=EvidenceType.LOG,
            side_effect_level=SideEffectLevel.READ,
            parallel_safe=True,
        ),
        input_schema={"type": "object", "properties": {}},
        output_schema={"type": "object", "properties": {}},
        call=lambda: None,
        source_module="capabilities.tools.example",
        source_qualname=name,
    )


def _skill(
    tmp_path: Path,
    name: str,
    *,
    directs: tuple[str, ...] = (),
    alert_sources: tuple[str, ...] = (),
    requires: Requirements = Requirements(),
) -> DiscoveredSkill:
    directory = tmp_path / name
    directory.mkdir(parents=True, exist_ok=True)
    manifest = directory / "SKILL.md"
    manifest.write_text(
        "---\n"
        f"name: {name}\n"
        "description: Statistics before samples.\n"
        "domain: observability\n"
        + (f"directs_tools: [{', '.join(directs)}]\n" if directs else "")
        + (
            f"applies_when:\n  alert_sources: [{', '.join(alert_sources)}]\n"
            if alert_sources
            else ""
        )
        + (
            f"requires:\n  integrations: [{', '.join(requires.integrations)}]\n"
            if requires.integrations
            else ""
        )
        + "---\n\nStart with statistics.\n",
        encoding="utf-8",
    )
    return load_skill(manifest)


# --- Resolution ---------------------------------------------------------------


def test_a_tool_whose_integration_is_unconfigured_is_excluded_with_a_reason() -> None:
    registry = Registry(
        tools={
            "datadog_read": _tool("datadog_read", requires=Requirements(integrations=("datadog",))),
            "splunk_read": _tool("splunk_read", requires=Requirements(integrations=("splunk",))),
        }
    )

    resolved = resolve_for(registry, ConfiguredIntegrations(integrations=("datadog",)))

    assert [found.name for found in resolved.tools] == ["datadog_read"]
    excluded = resolved.exclusion("splunk_read")
    assert excluded is not None
    assert excluded.unmet == ("splunk",)
    assert "splunk" in excluded.reason


def test_a_capability_requiring_nothing_is_available_to_every_team() -> None:
    registry = Registry(tools={"think": _tool("think", source=EvidenceSource.REASONING)})

    resolved = resolve_for(registry, ConfiguredIntegrations(integrations=()))

    assert len(resolved.tools) == 1


def test_a_skill_whose_every_tool_is_excluded_is_excluded_too(tmp_path: Path) -> None:
    """Otherwise the methodology reads as available and names tools that are not."""
    registry = Registry(
        tools={
            "splunk_read": _tool("splunk_read", requires=Requirements(integrations=("splunk",)))
        },
        skills={"splunk-method": _skill(tmp_path, "splunk-method", directs=("splunk_read",))},
    )

    resolved = resolve_for(registry, ConfiguredIntegrations(integrations=("datadog",)))

    assert resolved.skills == ()
    assert resolved.exclusion("splunk-method") is not None


def test_a_skill_that_directs_no_tools_survives_every_configuration(tmp_path: Path) -> None:
    """Pure methodology needs nothing configured, and is useful when nothing is."""
    registry = Registry(skills={"investigate": _skill(tmp_path, "investigate")})

    resolved = resolve_for(registry, ConfiguredIntegrations(integrations=()))

    assert [skill.name for skill in resolved.skills] == ["investigate"]


def test_a_sandbox_profile_a_deployment_lacks_excludes_the_tool() -> None:
    registry = Registry(
        tools={
            "run_python": _tool(
                "run_python", requires=Requirements(sandbox_profiles=("privileged",))
            )
        }
    )

    resolved = resolve_for(
        registry, ConfiguredIntegrations(integrations=(), sandbox_profiles=("restricted",))
    )

    assert resolved.tools == ()
    assert resolved.exclusion("run_python") is not None


# --- Scoring ------------------------------------------------------------------


def test_the_vendor_holding_the_subject_outweighs_tag_overlap_alone() -> None:
    """Tags are cheap to write and cheap to get wrong; a subject match is not.

    The subject's vendor is a fact the estate swept and alert resolution
    matched. Tags are prose an author typed, and three of them agreeing with
    an alert's labels is agreement about vocabulary rather than about what
    broke.
    """
    incident = Incident(subject_sources=("datadog",), tags=("logs", "latency", "errors"))

    matched = score_capability(_tool("datadog_read", source="datadog").metadata, incident)
    tagged = score_capability(
        _tool("splunk_read", source="splunk", tags=("logs", "latency", "errors")).metadata,
        incident,
    )

    assert matched.score > tagged.score


def test_who_reported_the_alert_never_outweighs_what_the_alert_is_about() -> None:
    """The notifier's own tools are relevant; they are not the most relevant.

    This inequality used to run the other way, and the arithmetic reached a
    deployment: a staging estate routed every alert through one Alertmanager,
    so every incident it ever had ranked that one vendor's tools first. An
    alert about failing Proxmox backup jobs offered the Alertmanager reads at
    the top of the list and cut the Proxmox backup read at zero, and the
    investigation concluded without reading the machine.

    Both terms still fire, and a capability that is both — the alerting
    system's own tools on an alerting-system subject — scores both.
    """
    incident = Incident(alert_source="alertmanager", subject_sources=("proxmox",))

    reporter = score_capability(
        _tool("alertmanager_read", source="alertmanager").metadata, incident
    )
    subject = score_capability(_tool("proxmox_read", source="proxmox").metadata, incident)

    assert reporter.score > 0.0, "reading the alerting system about an alert is worth something"
    assert subject.score > reporter.score, (
        "the system that reported a failure outranked the system that has it. A "
        "deployment with one alert receiver ranks that receiver first for every "
        "incident it will ever have."
    )


def test_an_anti_example_describing_the_incident_suppresses_the_capability() -> None:
    incident = Incident(
        alert_source="datadog", summary="Customer reports a billing discrepancy on invoices."
    )
    scored = score_capability(
        _tool(
            "datadog_read",
            source="datadog",
            anti_examples=("billing discrepancy invoices",),
        ).metadata,
        incident,
    )

    assert scored.suppressed


def test_a_partial_anti_example_match_is_a_coincidence_not_a_veto() -> None:
    incident = Incident(alert_source="datadog", summary="Checkout latency is up.")
    scored = score_capability(
        _tool(
            "datadog_read", source="datadog", anti_examples=("billing discrepancy invoices",)
        ).metadata,
        incident,
    )

    assert not scored.suppressed


def test_the_neutral_effectiveness_default_degrades_to_source_and_tag_matching() -> None:
    """Feature 010 is not here yet, and selection cannot wait for it."""
    incident = Incident(alert_source="datadog", tags=("logs",))

    without = score_capability(_tool("datadog_read").metadata, incident)
    with_neutral = score_capability(_tool("datadog_read").metadata, incident, effectiveness=None)

    assert without == with_neutral
    assert without.score > 0.0


def test_a_learned_effectiveness_signal_raises_a_capability() -> None:
    class Learned:
        def effectiveness(self, capability: str, *, alert_source: str) -> float:
            return 1.0 if capability == "datadog_read" else 0.0

    incident = Incident(alert_source="datadog")
    learned = score_capability(_tool("datadog_read").metadata, incident, effectiveness=Learned())
    neutral = score_capability(_tool("datadog_read").metadata, incident)

    assert learned.score > neutral.score
    assert any("historically effective" in reason for reason in learned.rationale)


def test_scoring_records_why_rather_than_only_how_much() -> None:
    scored = score_capability(
        _tool("datadog_read", tags=("logs",), domain="observability").metadata,
        Incident(alert_source="datadog", tags=("logs",), domain="observability"),
    )

    assert len(scored.rationale) == 3


def test_ranking_is_deterministic_including_the_ties() -> None:
    """SC-005. Without a tiebreak, two equal capabilities order by luck."""
    catalogue = [_tool(name).metadata for name in ("charlie", "alpha", "bravo")]
    incident = Incident(alert_source="datadog")

    first = [scored.name for scored in rank(catalogue, incident)]
    second = [scored.name for scored in rank(list(reversed(catalogue)), incident)]

    assert first == second == ["alpha", "bravo", "charlie"]


# --- Selection ----------------------------------------------------------------


def _secondary(name: str) -> RegisteredTool:
    return _tool(name, source=sorted(SECONDARY_EVIDENCE_SOURCES)[0])


def test_the_cap_holds_with_four_hundred_capabilities_registered() -> None:
    """SC-001, at the scale the catalogue is actually designed for."""
    catalogue = ResolvedCatalogue(
        tools=tuple(_tool(f"vendor_tool_{index:03d}") for index in range(395))
        + tuple(_secondary(f"reasoning_tool_{index}") for index in range(5))
    )

    result = select(catalogue, Incident(alert_source="datadog"))

    assert len(result.tools) == MAX_AGENT_TOOL_SCHEMAS
    assert len(result.tool_schemas()) == MAX_AGENT_TOOL_SCHEMAS


def test_the_reserve_is_populated_even_when_vendor_tools_score_higher() -> None:
    """FR-014. This is the case the reserve exists for and the only one."""
    catalogue = ResolvedCatalogue(
        tools=tuple(
            _tool(f"datadog_tool_{index:03d}", source="datadog", tags=("logs",))
            for index in range(395)
        )
        + tuple(_secondary(f"reasoning_tool_{index}") for index in range(5))
    )

    result = select(catalogue, Incident(alert_source="datadog", tags=("logs",)))

    assert len(result.secondary) == MAX_SECONDARY_FALLBACK_TOOLS


def test_a_plan_entry_is_taken_before_anything_scored() -> None:
    catalogue = ResolvedCatalogue(
        tools=tuple(_tool(f"datadog_tool_{index:03d}") for index in range(100))
        + (_tool("obscure_tool", source="nothing_matches"),)
    )

    result = select(
        catalogue, Incident(alert_source="datadog", planned_capabilities=("obscure_tool",))
    )

    assert "obscure_tool" in {found.name for found in result.tools}
    assert result.rationale[0] == "obscure_tool: named by the plan"


def test_selecting_a_skill_brings_the_tools_it_directs(tmp_path: Path) -> None:
    """FR-015. A methodology naming tools the model cannot call is worse than none."""
    catalogue = ResolvedCatalogue(
        tools=(
            _tool("datadog_log_statistics", source="datadog"),
            _tool("datadog_sample_logs", source="datadog"),
        )
        + tuple(_tool(f"noise_{index:03d}", source="other") for index in range(100)),
        skills=(
            _skill(
                tmp_path,
                "observability-datadog",
                directs=("datadog_log_statistics", "datadog_sample_logs"),
                alert_sources=("datadog",),
            ),
        ),
    )

    result = select(catalogue, Incident(alert_source="datadog"))

    selected = {found.name for found in result.tools}
    assert {"datadog_log_statistics", "datadog_sample_logs"} <= selected
    assert [skill.name for skill in result.skills] == ["observability-datadog"]


def test_skill_expansion_still_respects_the_cap(tmp_path: Path) -> None:
    directed = tuple(f"directed_{index:03d}" for index in range(200))
    catalogue = ResolvedCatalogue(
        tools=tuple(_tool(name, source="datadog") for name in directed),
        skills=(_skill(tmp_path, "greedy-skill", directs=directed, alert_sources=("datadog",)),),
    )

    result = select(catalogue, Incident(alert_source="datadog"))

    assert len(result.tools) == MAX_AGENT_TOOL_SCHEMAS


def test_a_skill_body_is_loaded_only_for_a_selected_skill(tmp_path: Path) -> None:
    catalogue = ResolvedCatalogue(
        skills=(
            _skill(tmp_path, "chosen", alert_sources=("datadog",)),
            _skill(tmp_path, "ignored", alert_sources=("pagerduty",)),
        ),
    )

    result = select(catalogue, Incident(alert_source="datadog"))
    bodies = dict(result.skill_bodies())

    assert set(bodies) == {"chosen"}


def test_selection_is_deterministic(tmp_path: Path) -> None:
    """SC-005, at the level a trajectory comparison actually depends on."""
    catalogue = ResolvedCatalogue(
        tools=tuple(_tool(f"tool_{index:03d}", source="datadog") for index in range(80)),
        skills=(_skill(tmp_path, "observability-datadog", alert_sources=("datadog",)),),
    )
    incident = Incident(alert_source="datadog", tags=("logs",), summary="Checkout latency is up.")

    first = select(catalogue, incident)
    second = select(catalogue, incident)

    assert [found.name for found in first.tools] == [found.name for found in second.tools]
    assert first.rationale == second.rationale


def test_every_selected_capability_carries_its_reason() -> None:
    catalogue = ResolvedCatalogue(tools=(_tool("datadog_read"), _secondary("recall")))

    result = select(catalogue, Incident(alert_source="datadog"))

    explained = {line.split(":", 1)[0] for line in result.rationale}
    assert {found.name for found in result.tools} <= explained


def test_the_trace_record_keeps_the_scores_of_what_was_not_chosen() -> None:
    """The question after a bad investigation is why something was not offered."""
    catalogue = ResolvedCatalogue(tools=tuple(_tool(f"tool_{index:03d}") for index in range(60)))

    record = selection_record(select(catalogue, Incident(alert_source="datadog")))

    assert len(record["scores"]) == 60  # type: ignore[arg-type]
    assert len(record["tools"]) == MAX_AGENT_TOOL_SCHEMAS  # type: ignore[arg-type]


def test_a_reserve_that_leaves_no_room_is_refused() -> None:
    with pytest.raises(SelectionError, match="reserve"):
        select(ResolvedCatalogue(), Incident(), max_schemas=4, reserved=4)


def test_an_empty_catalogue_selects_nothing_rather_than_failing() -> None:
    """Selection when the alert carries no source hint at all."""
    result = select(ResolvedCatalogue(), Incident())

    assert result.tools == ()
    assert result.skills == ()


def test_an_alert_with_no_source_still_selects_by_score() -> None:
    catalogue = ResolvedCatalogue(tools=tuple(_tool(f"tool_{index:02d}") for index in range(50)))

    result = select(catalogue, Incident(summary="Something is wrong somewhere."))

    assert len(result.tools) == MAX_AGENT_TOOL_SCHEMAS


def test_a_suppressed_capability_can_still_be_taken_by_name() -> None:
    """A plan naming a capability knows something the declaration did not."""
    suppressed = _tool("billing_lookup", anti_examples=("checkout latency spike",), source="stripe")
    catalogue = ResolvedCatalogue(tools=(suppressed, _tool("datadog_read")))

    result = select(
        catalogue,
        Incident(
            alert_source="datadog",
            summary="Checkout latency spike.",
            planned_capabilities=("billing_lookup",),
        ),
    )

    assert "billing_lookup" in {found.name for found in result.tools}


def test_a_suppressed_capability_is_not_offered_on_score_alone() -> None:
    suppressed = _tool(
        "billing_lookup",
        source="datadog",
        anti_examples=("checkout latency spike",),
    )
    catalogue = ResolvedCatalogue(tools=(suppressed, _tool("datadog_read", source="datadog")))

    result = select(catalogue, Incident(alert_source="datadog", summary="Checkout latency spike."))

    assert "billing_lookup" not in {found.name for found in result.tools}


def test_a_skill_and_its_metadata_are_scored_in_one_catalogue(tmp_path: Path) -> None:
    """One selection path over both kinds, which is what makes the hybrid work."""
    catalogue = ResolvedCatalogue(
        tools=(_tool("datadog_read", source="datadog"),),
        skills=(_skill(tmp_path, "observability-datadog", alert_sources=("datadog",)),),
    )

    result = select(catalogue, Incident(alert_source="datadog"))

    assert {scored.name for scored in result.scores} == {"datadog_read", "observability-datadog"}


def test_skill_metadata_is_scored_on_what_it_applies_to() -> None:
    metadata = SkillMetadata(
        name="observability-datadog",
        display_name="Datadog investigation",
        description="Statistics before samples.",
        domain="observability",
        applies_when=AppliesWhen(alert_sources=("datadog",), tags=("logs",)),
    )

    matching = score_capability(metadata, Incident(alert_source="datadog"))
    other = score_capability(metadata, Incident(alert_source="pagerduty"))

    assert matching.score > other.score
