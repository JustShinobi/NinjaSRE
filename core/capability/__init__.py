"""The capability framework: what a tool is, what a skill is, and what both owe.

Tier 3. This package owns the *primitives* — the declaration types, the two
ways of declaring a tool, the result and trace shapes, and the ports that let a
selector run before the features feeding it exist. It owns no capabilities and
no catalogue: discovery, validation, scoring, and selection are tier 2, in
``capabilities/registry/``, because they walk packages that sit above this one.

The split is what lets an integration declare a tool without importing the
registry, and the registry find it without the integration knowing it exists.

    from core.capability import SideEffectLevel, tool

    @tool(
        name="datadog_log_statistics",
        display_name="Datadog log statistics",
        description="Aggregate counts over a log query before sampling any lines.",
        evidence_source="datadog",
        evidence_type=EvidenceType.LOG,
        side_effect_level=SideEffectLevel.READ,
        parallel_safe=True,
    )
    async def datadog_log_statistics(query: str) -> dict[str, int]:
        ...
"""

from __future__ import annotations

from core.capability.base import BaseTool
from core.capability.decorator import tool
from core.capability.metadata import (
    AppliesWhen,
    CapabilityKind,
    CapabilityMetadata,
    EvidenceSource,
    EvidenceType,
    ExcludedCapability,
    Requirements,
    RollbackPlan,
    RollbackPlanner,
    SideEffectLevel,
    SkillMetadata,
    ToolMetadata,
    metadata_text,
)
from core.capability.ports import (
    ConfiguredIntegrations,
    EffectivenessProvider,
    IntegrationAvailability,
    NeutralEffectiveness,
    validate_effectiveness,
)
from core.capability.registered import RegisteredTool, capability_marker, mark_capability
from core.capability.result import (
    CapabilityError,
    CapabilityErrorClass,
    CapabilityResult,
    Evidence,
)
from core.capability.schema import SchemaError, derive_input_schema, derive_output_schema
from core.capability.telemetry import (
    CapabilityInvocation,
    InvocationOutcome,
    filter_arguments,
    record_invocation,
)
from core.capability.tokens import TokenCounter, estimate_tokens
from core.capability.types import Capability, Skill, Tool

__all__ = [
    "AppliesWhen",
    "BaseTool",
    "Capability",
    "CapabilityError",
    "CapabilityErrorClass",
    "CapabilityInvocation",
    "CapabilityKind",
    "CapabilityMetadata",
    "CapabilityResult",
    "ConfiguredIntegrations",
    "EffectivenessProvider",
    "Evidence",
    "EvidenceSource",
    "EvidenceType",
    "ExcludedCapability",
    "IntegrationAvailability",
    "InvocationOutcome",
    "NeutralEffectiveness",
    "RegisteredTool",
    "Requirements",
    "RollbackPlan",
    "RollbackPlanner",
    "SchemaError",
    "SideEffectLevel",
    "Skill",
    "SkillMetadata",
    "TokenCounter",
    "Tool",
    "ToolMetadata",
    "capability_marker",
    "derive_input_schema",
    "derive_output_schema",
    "estimate_tokens",
    "filter_arguments",
    "mark_capability",
    "metadata_text",
    "record_invocation",
    "tool",
    "validate_effectiveness",
]
