"""Every way a catalogue can be wrong, and the distinct message each produces.

This is SC-004 written down. The value of a build-time gate is not that it
fails — it is that the failure says which of nine things happened, to which
capability, and where the other one is. "Validation failed" sends a contributor
back to read the whole feature; "duplicate-tool-name: datadog_query_metrics:
declared in A and B" sends them to two lines.

So each rule gets a fixture, and each fixture asserts on the message rather
than only on the exception type.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from capabilities.registry import validation
from capabilities.registry.disclosure import DiscoveredSkill, load_skill
from capabilities.registry.discovery import DiscoveredCatalogue
from capabilities.registry.validation import ValidationError, failures, rules, validate
from config.constants.capabilities import (
    MAX_CATALOGUE_METADATA_TOKENS,
    MAX_SKILL_METADATA_TOKENS,
)
from core.capability.decorator import tool
from core.capability.metadata import (
    EvidenceType,
    Requirements,
    SideEffectLevel,
    SkillMetadata,
    ToolMetadata,
)
from core.capability.registered import RegisteredTool, capability_marker

pytestmark = pytest.mark.unit


def _tool(
    name: str,
    *,
    module: str = "capabilities.tools.example",
    description: str = "Reads something and reports what it read.",
    requires: Requirements = Requirements(),
) -> RegisteredTool:
    """Return a registered tool standing in for a discovered one."""
    return RegisteredTool(
        metadata=ToolMetadata(
            name=name,
            display_name=name,
            description=description,
            evidence_source="datadog",
            evidence_type=EvidenceType.LOG,
            side_effect_level=SideEffectLevel.READ,
            parallel_safe=True,
            requires=requires,
        ),
        input_schema={"type": "object", "properties": {}},
        output_schema={"type": "object", "properties": {}},
        call=lambda: None,
        source_module=module,
        source_qualname=name,
    )


def _skill(
    tmp_path: Path,
    *,
    name: str = "observability-datadog",
    description: str = "Statistics before samples.",
    directs: str = "",
    requires: str = "",
    body: str = "Start with statistics.",
    subdirectory: str = "",
) -> object:
    """Write a manifest and return the loaded skill."""
    directory = tmp_path / subdirectory / name if subdirectory else tmp_path / name
    directory.mkdir(parents=True, exist_ok=True)
    manifest = directory / "SKILL.md"
    manifest.write_text(
        "---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        "domain: observability\n"
        f"{directs}"
        f"{requires}"
        "---\n\n"
        f"{body}\n",
        encoding="utf-8",
    )
    return load_skill(manifest)


def test_a_clean_catalogue_passes_and_is_returned() -> None:
    catalogue = DiscoveredCatalogue(tools=(_tool("datadog_query_metrics"),))

    assert validate(catalogue) is catalogue


def test_a_duplicate_tool_name_names_both_sources() -> None:
    catalogue = DiscoveredCatalogue(
        tools=(
            _tool("datadog_query_metrics", module="integrations.datadog.tools.metrics"),
            _tool("datadog_query_metrics", module="capabilities.tools.cross_vendor.metrics"),
        )
    )

    with pytest.raises(ValidationError) as raised:
        validate(catalogue)

    message = str(raised.value)
    assert validation.DUPLICATE_TOOL_NAME in message
    assert "integrations.datadog.tools.metrics" in message
    assert "capabilities.tools.cross_vendor.metrics" in message


def test_a_duplicate_skill_name_names_both_manifests(tmp_path: Path) -> None:
    """Two skills, two directories, one name — and one of them would never load."""
    catalogue = DiscoveredCatalogue(
        skills=(  # type: ignore[arg-type]
            _skill(tmp_path, subdirectory="shipped"),
            _skill(tmp_path, subdirectory="local"),
        ),
    )

    with pytest.raises(ValidationError) as raised:
        validate(catalogue)

    message = str(raised.value)
    assert validation.DUPLICATE_SKILL_NAME in message
    assert "shipped" in message
    assert "local" in message


def test_a_dangling_directed_tool_names_the_skill_and_the_tool(tmp_path: Path) -> None:
    catalogue = DiscoveredCatalogue(
        tools=(_tool("datadog_log_statistics"),),
        skills=(_skill(tmp_path, directs="directs_tools: [datadog_log_statistics, typo_tool]\n"),),  # type: ignore[arg-type]
    )

    with pytest.raises(ValidationError) as raised:
        validate(catalogue)

    message = str(raised.value)
    assert validation.DANGLING_DIRECTED_TOOL in message
    assert "observability-datadog" in message
    assert "typo_tool" in message


def test_a_tool_declared_without_a_side_effect_level_cannot_be_built() -> None:
    """The failure lands at import, which is where a build failure belongs."""
    with pytest.raises(TypeError, match="side_effect_level"):

        @tool(  # type: ignore[call-arg]
            name="undeclared",
            display_name="Undeclared",
            description="Says nothing about what it does to the world.",
            evidence_source="datadog",
            evidence_type=EvidenceType.LOG,
            parallel_safe=True,
        )
        async def undeclared() -> None:
            return None


def test_a_write_tool_without_approval_metadata_cannot_be_built() -> None:
    with pytest.raises(ValueError, match="requires_approval"):

        @tool(
            name="restarts_things",
            display_name="Restarts things",
            description="Restarts a deployment, dropping in-flight requests.",
            evidence_source="kubernetes",
            evidence_type=EvidenceType.CHANGE,
            side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
            parallel_safe=False,
        )
        async def restarts_things() -> None:
            return None


def test_a_write_tool_without_a_rollback_plan_cannot_be_built() -> None:
    with pytest.raises(ValueError, match="rollback"):

        @tool(
            name="restarts_things",
            display_name="Restarts things",
            description="Restarts a deployment, dropping in-flight requests.",
            evidence_source="kubernetes",
            evidence_type=EvidenceType.CHANGE,
            side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
            parallel_safe=False,
            requires_approval=True,
            approval_reason="Restarting drops in-flight requests.",
        )
        async def restarts_things() -> None:
            return None


def test_a_complete_write_declaration_reaches_the_catalogue() -> None:
    @tool(
        name="restarts_deployment",
        display_name="Restarts a deployment",
        description="Restarts a deployment, dropping in-flight requests.",
        evidence_source="kubernetes",
        evidence_type=EvidenceType.CHANGE,
        side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
        parallel_safe=False,
        requires_approval=True,
        approval_reason="Restarting drops in-flight requests.",
        rollback_plan="Scale the previous ReplicaSet back up.",
    )
    async def restarts_deployment(deployment: str) -> None:
        return None

    registered = capability_marker(restarts_deployment)
    assert registered is not None
    assert validate(DiscoveredCatalogue(tools=(registered,)))


def test_an_oversized_skill_index_entry_is_rejected(tmp_path: Path) -> None:
    catalogue = DiscoveredCatalogue(
        skills=(_skill(tmp_path, description="Detail. " * 200),),  # type: ignore[arg-type]
    )

    with pytest.raises(ValidationError) as raised:
        validate(catalogue)

    message = str(raised.value)
    assert validation.SKILL_METADATA_OVER_BUDGET in message
    assert str(MAX_SKILL_METADATA_TOKENS) in message


def test_a_skill_body_instructing_shell_is_rejected(tmp_path: Path) -> None:
    catalogue = DiscoveredCatalogue(
        skills=(  # type: ignore[arg-type]
            _skill(tmp_path, body="Run `kubectl delete pod checkout-api` to clear it."),
        ),
    )

    with pytest.raises(ValidationError) as raised:
        validate(catalogue)

    assert validation.SKILL_BODY_INSTRUCTS_SHELL in str(raised.value)


def test_a_skill_requiring_more_than_its_tools_is_rejected(tmp_path: Path) -> None:
    catalogue = DiscoveredCatalogue(
        tools=(_tool("datadog_log_statistics", requires=Requirements(integrations=("datadog",))),),
        skills=(  # type: ignore[arg-type]
            _skill(
                tmp_path,
                directs="directs_tools: [datadog_log_statistics]\n",
                requires="requires:\n  integrations: [datadog, splunk]\n",
            ),
        ),
    )

    with pytest.raises(ValidationError) as raised:
        validate(catalogue)

    message = str(raised.value)
    assert validation.SKILL_REQUIRES_NOT_COVERED in message
    assert "splunk" in message


def test_a_name_claimed_by_both_kinds_is_rejected(tmp_path: Path) -> None:
    catalogue = DiscoveredCatalogue(
        tools=(_tool("investigate"),),
        skills=(_skill(tmp_path, name="investigate"),),  # type: ignore[arg-type]
    )

    with pytest.raises(ValidationError) as raised:
        validate(catalogue)

    assert validation.NAME_USED_BY_BOTH_KINDS in str(raised.value)


def test_an_oversized_tool_description_is_rejected() -> None:
    catalogue = DiscoveredCatalogue(
        tools=(_tool("verbose_tool", description="A sentence of explanation. " * 200),)
    )

    with pytest.raises(ValidationError) as raised:
        validate(catalogue)

    assert validation.TOOL_DESCRIPTION_OVER_BUDGET in str(raised.value)


def test_a_catalogue_over_the_total_budget_is_rejected(tmp_path: Path) -> None:
    """SC-002 as a gate rather than an estimate.

    Each entry can be inside its own ceiling while the index as a whole is not,
    which is exactly how a context budget is exhausted one integration at a
    time with every individual review passing.
    """
    at_the_ceiling = tuple(
        DiscoveredSkill(
            metadata=SkillMetadata(
                name=f"skill-{index:03d}",
                display_name=f"Skill {index}",
                description="Statistics before samples.",
                domain="observability",
            ),
            path=tmp_path / f"skill-{index:03d}" / "SKILL.md",
            metadata_tokens=MAX_SKILL_METADATA_TOKENS,
        )
        for index in range(1 + MAX_CATALOGUE_METADATA_TOKENS // MAX_SKILL_METADATA_TOKENS)
    )

    with pytest.raises(ValidationError) as raised:
        validate(DiscoveredCatalogue(skills=at_the_ceiling), check_bodies=False)

    assert validation.CATALOGUE_METADATA_OVER_BUDGET in str(raised.value)


def test_tool_descriptions_do_not_count_against_the_standing_index() -> None:
    """A tool's prose is paid for when it is selected, and selection is capped.

    Counting it here would fire the ceiling on a catalogue that fits, and the
    remedy a contributor would reach for — shortening tool descriptions — would
    not reduce what a turn actually costs.
    """
    many = tuple(
        _tool(f"tool_{index}", description="Reads a thing and reports what it read.")
        for index in range(4_000)
    )

    assert validate(DiscoveredCatalogue(tools=many))


def test_all_failures_are_reported_together(tmp_path: Path) -> None:
    """Six manifests fixed in one pass, rather than six build runs."""
    catalogue = DiscoveredCatalogue(
        tools=(
            _tool("datadog_query_metrics", module="a.b"),
            _tool("datadog_query_metrics", module="c.d"),
        ),
        skills=(  # type: ignore[arg-type]
            _skill(
                tmp_path,
                directs="directs_tools: [missing_tool]\n",
                body="Run `bash cleanup.sh` first.",
            ),
        ),
    )

    reported = failures(catalogue)
    fired = {failure.rule for failure in reported}

    assert validation.DUPLICATE_TOOL_NAME in fired
    assert validation.DANGLING_DIRECTED_TOOL in fired
    assert validation.SKILL_BODY_INSTRUCTS_SHELL in fired


def test_the_error_names_every_rule_that_fired(tmp_path: Path) -> None:
    catalogue = DiscoveredCatalogue(
        tools=(_tool("t", module="a.b"), _tool("t", module="c.d")),
    )

    with pytest.raises(ValidationError) as raised:
        validate(catalogue)

    assert raised.value.failures
    assert all(failure.rule in rules() for failure in raised.value.failures)


def test_every_declared_rule_has_a_fixture_here() -> None:
    """A rule with no fixture is a rule nobody has seen fire.

    This is the check that keeps SC-004 true as rules are added: the tenth rule
    fails this test until somebody writes the case that produces it.
    """
    source = Path(__file__).read_text(encoding="utf-8")
    uncovered = [rule for rule in rules() if rule.replace("-", "_").upper() not in source]

    assert uncovered == []
