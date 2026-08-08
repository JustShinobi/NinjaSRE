"""Capability metadata is a declaration, and the dangerous field has no default.

The whole safety argument of the catalogue rests on one property: a tool that
does not say what it does to the world cannot be built. Absence is never
permission, so there is nothing to forget to write down — omitting the level is
a build failure rather than a quiet promotion to read.
"""

from __future__ import annotations

import dataclasses

import pytest

from core.capability.metadata import (
    AppliesWhen,
    CapabilityKind,
    CapabilityMetadata,
    EvidenceSource,
    EvidenceType,
    Requirements,
    SideEffectLevel,
    SkillMetadata,
    ToolMetadata,
)

pytestmark = pytest.mark.unit


def _tool(**overrides: object) -> ToolMetadata:
    """Return a minimal valid tool declaration, with ``overrides`` applied."""
    declaration: dict[str, object] = {
        "name": "datadog_log_statistics",
        "display_name": "Datadog log statistics",
        "description": "Aggregate counts over a log query before sampling any lines.",
        "evidence_source": "datadog",
        "evidence_type": EvidenceType.LOG,
        "side_effect_level": SideEffectLevel.READ,
        "parallel_safe": True,
    }
    declaration.update(overrides)
    return ToolMetadata(**declaration)  # type: ignore[arg-type]


def test_the_side_effect_scale_is_closed_and_ordered() -> None:
    assert [member.value for member in SideEffectLevel] == [
        "read",
        "read_sensitive",
        "write_reversible",
        "write_irreversible",
        "destructive",
    ]


def test_side_effect_levels_compare_by_danger() -> None:
    assert SideEffectLevel.READ < SideEffectLevel.READ_SENSITIVE
    assert SideEffectLevel.WRITE_REVERSIBLE < SideEffectLevel.DESTRUCTIVE
    assert max(SideEffectLevel) is SideEffectLevel.DESTRUCTIVE


@pytest.mark.parametrize(
    ("level", "needs_approval"),
    [
        (SideEffectLevel.READ, False),
        (SideEffectLevel.READ_SENSITIVE, False),
        (SideEffectLevel.WRITE_REVERSIBLE, True),
        (SideEffectLevel.WRITE_IRREVERSIBLE, True),
        (SideEffectLevel.DESTRUCTIVE, True),
    ],
)
def test_everything_above_read_sensitive_is_approval_gated(
    level: SideEffectLevel, needs_approval: bool
) -> None:
    assert level.needs_approval is needs_approval


def test_side_effect_level_has_no_default() -> None:
    """The one field that must never be inferred, asserted structurally.

    A test that merely omits the argument would also pass if somebody later
    added a default and a validator that filled it in. This reads the dataclass
    itself, so the guarantee cannot be reintroduced by another route.
    """
    fields = {field.name: field for field in dataclasses.fields(ToolMetadata)}
    side_effect_level = fields["side_effect_level"]

    assert side_effect_level.default is dataclasses.MISSING
    assert side_effect_level.default_factory is dataclasses.MISSING


def test_a_tool_without_a_side_effect_level_cannot_be_declared() -> None:
    with pytest.raises(TypeError):
        ToolMetadata(  # type: ignore[call-arg]
            name="rogue",
            display_name="Rogue",
            description="Declares nothing about what it does.",
            evidence_source="none",
            evidence_type=EvidenceType.ANALYSIS,
            parallel_safe=True,
        )


def test_a_write_tool_must_carry_approval_metadata() -> None:
    with pytest.raises(ValueError, match="requires_approval"):
        _tool(
            name="kubernetes_restart_deployment",
            side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
        )


def test_a_write_tool_must_say_why_approval_is_needed() -> None:
    with pytest.raises(ValueError, match="approval_reason"):
        _tool(
            name="kubernetes_restart_deployment",
            side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
            requires_approval=True,
        )


def test_a_write_tool_must_declare_a_rollback_plan_generator() -> None:
    with pytest.raises(ValueError, match="rollback"):
        _tool(
            name="kubernetes_restart_deployment",
            side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
            requires_approval=True,
            approval_reason="Restarting a deployment drops in-flight requests.",
        )


def test_a_write_tool_must_declare_how_dangerous_it_is() -> None:
    with pytest.raises(ValueError, match="risk_class"):
        _tool(
            name="kubernetes_restart_deployment",
            side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
            requires_approval=True,
            approval_reason="Restarting a deployment drops in-flight requests.",
            rollback_plan="Scale the previous ReplicaSet back up and delete the new one.",
        )


def test_a_complete_write_declaration_is_accepted() -> None:
    metadata = _tool(
        name="kubernetes_restart_deployment",
        side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
        requires_approval=True,
        approval_reason="Restarting a deployment drops in-flight requests.",
        rollback_plan="Scale the previous ReplicaSet back up and delete the new one.",
        risk_class="moderate",
    )

    assert metadata.side_effect_level.needs_approval
    assert metadata.rollback_plan
    assert metadata.risk_class == "moderate"


def test_a_read_tool_may_not_claim_approval_it_does_not_need() -> None:
    """Approval noise is not free: it trains an operator to click through.

    A read tool declaring ``requires_approval`` would put a human in front of a
    query that changes nothing, and the next prompt they see is a restart.
    """
    with pytest.raises(ValueError, match="read"):
        _tool(requires_approval=True, approval_reason="Not actually needed.")


def test_metadata_is_immutable() -> None:
    metadata = _tool()
    with pytest.raises(dataclasses.FrozenInstanceError):
        metadata.name = "renamed"  # type: ignore[misc]


def test_a_tool_name_must_be_callable_by_a_model() -> None:
    with pytest.raises(ValueError, match="name"):
        _tool(name="Datadog Log Statistics!")


def test_a_tool_name_may_not_carry_a_hyphen() -> None:
    """The model emits a tool name as a symbol; a hyphen makes it unemittable.

    Leaving it to the provider normaliser to rewrite would work, and would also
    mean the name in the trace is not the name in the declaration.
    """
    with pytest.raises(ValueError, match="name"):
        _tool(name="datadog-log-statistics")


def test_a_skill_name_may_carry_a_hyphen() -> None:
    """A skill is selected, never called, so it is an identifier rather than a symbol."""
    skill = SkillMetadata(
        name="observability-datadog",
        display_name="Datadog investigation",
        description="Statistics before samples.",
        domain="observability",
    )

    assert skill.name == "observability-datadog"


def test_a_capability_must_describe_itself() -> None:
    with pytest.raises(ValueError, match="description"):
        _tool(description="   ")


def test_a_tool_must_name_the_system_its_evidence_came_from() -> None:
    with pytest.raises(ValueError, match="evidence_source"):
        _tool(evidence_source="")


def test_evidence_sources_are_open_but_the_common_ones_are_named() -> None:
    """Vendors bring their own source names; the shared ones still have a home.

    Closing this set would mean editing a central enum for every integration,
    which is the one thing FR-010 exists to prevent.
    """
    assert _tool(evidence_source=EvidenceSource.REASONING).evidence_source == "reasoning"
    assert _tool(evidence_source="a-vendor-nobody-has-written-yet").evidence_source


def test_prose_fields_default_to_empty_rather_than_none() -> None:
    metadata = _tool()

    assert metadata.use_cases == ()
    assert metadata.anti_examples == ()
    assert metadata.tags == ()
    assert metadata.requires == Requirements()


def test_declared_sequences_are_frozen_into_tuples() -> None:
    """A mutable default on a shared declaration is a cross-run data leak."""
    metadata = _tool(tags=["logs", "latency"], use_cases=["Find the failing endpoint"])

    assert metadata.tags == ("logs", "latency")
    assert metadata.use_cases == ("Find the failing endpoint",)


def test_a_skill_declares_the_tools_it_directs() -> None:
    skill = SkillMetadata(
        name="observability-datadog",
        display_name="Datadog investigation",
        description="Statistics before samples.",
        domain="observability",
        applies_when=AppliesWhen(alert_sources=("datadog",), tags=("logs",)),
        directs_tools=("datadog_log_statistics",),
        requires=Requirements(integrations=("datadog",)),
    )

    assert skill.kind is CapabilityKind.SKILL
    assert skill.directs_tools == ("datadog_log_statistics",)


def test_a_skill_may_direct_no_tools_at_all() -> None:
    """Pure methodology is a capability. It shapes reasoning and calls nothing."""
    skill = SkillMetadata(
        name="investigate",
        display_name="Investigation methodology",
        description="The five phases every investigation moves through.",
        domain="methodology",
    )

    assert skill.directs_tools == ()


def test_a_skill_must_declare_a_domain() -> None:
    with pytest.raises(ValueError, match="domain"):
        SkillMetadata(
            name="orphan",
            display_name="Orphan",
            description="Belongs nowhere.",
            domain="",
        )


def test_tool_and_skill_share_one_supertype() -> None:
    assert isinstance(_tool(), CapabilityMetadata)
    assert _tool().kind is CapabilityKind.TOOL
