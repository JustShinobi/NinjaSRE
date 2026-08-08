"""Every capability that can change something says how dangerous that is.

Declared at registration, checked over the whole discovered catalogue rather
than over a list somebody maintains here. A new remediation tool that lands
without a risk class fails this suite on the day it lands, which is the only
moment at which fixing it is cheap.

Reads are deliberately not required to declare one. Nothing that cannot change
anything reaches the autonomy resolver, and requiring a field on two hundred
read tools would teach authors to fill it in without thinking — which is exactly
how the field on the tool that mattered ends up wrong.
"""

from __future__ import annotations

import pytest

from capabilities.registry.catalogue import build_registry
from config.constants.autonomy import RISK_CLASSES
from core.capability.metadata import ToolMetadata
from platform.autonomy.risk import RiskClass, risk_class_of


def gated_tools() -> tuple[ToolMetadata, ...]:
    """Return every discovered tool that needs an approval or an autonomy rule."""
    registry = build_registry()
    return tuple(
        registry.tools[name].metadata
        for name in sorted(registry.tools)
        if registry.tools[name].metadata.side_effect_level.needs_approval
    )


def test_the_catalogue_has_tools_that_change_things_at_all() -> None:
    """A guard on the guard: an empty catalogue would pass everything below."""
    assert len(gated_tools()) >= 8


@pytest.mark.parametrize("metadata", gated_tools(), ids=lambda item: item.name)
def test_every_capability_that_changes_something_declares_a_risk_class(
    metadata: ToolMetadata,
) -> None:
    assert metadata.risk_class, (
        f"{metadata.name} is a {metadata.side_effect_level.value} tool with no declared "
        f"risk class. It would be treated as {RiskClass.CRITICAL.value} and never run "
        f"unattended — say what it actually is, from {', '.join(RISK_CLASSES)}."
    )
    assert metadata.risk_class in RISK_CLASSES


def test_a_declaration_that_is_not_a_risk_class_is_refused_at_registration() -> None:
    from core.capability.metadata import EvidenceType, SideEffectLevel

    with pytest.raises(ValueError, match="not a risk class"):
        ToolMetadata(
            name="reckless_tool",
            display_name="Reckless",
            description="Does something.",
            evidence_source="control_plane",
            evidence_type=EvidenceType.CHANGE,
            side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
            parallel_safe=False,
            requires_approval=True,
            approval_reason="It changes something.",
            rollback_plan="Undo it.",
            risk_class="reckless",
        )


def test_a_gated_tool_with_no_risk_class_is_refused_at_registration() -> None:
    """Absence is caught where it is cheap, and treated as critical where it is not."""
    from core.capability.metadata import EvidenceType, SideEffectLevel

    with pytest.raises(ValueError, match="risk_class"):
        ToolMetadata(
            name="unclassified_tool",
            display_name="Unclassified",
            description="Does something.",
            evidence_source="control_plane",
            evidence_type=EvidenceType.CHANGE,
            side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
            parallel_safe=False,
            requires_approval=True,
            approval_reason="It changes something.",
            rollback_plan="Undo it.",
        )


def test_a_read_tool_needs_no_risk_class_and_still_resolves_to_the_highest() -> None:
    from core.capability.metadata import EvidenceType, SideEffectLevel

    metadata = ToolMetadata(
        name="read_tool",
        display_name="Read",
        description="Reads something.",
        evidence_source="control_plane",
        evidence_type=EvidenceType.METRIC,
        side_effect_level=SideEffectLevel.READ,
        parallel_safe=True,
    )
    assert metadata.risk_class == ""
    assert risk_class_of(metadata.risk_class) is RiskClass.CRITICAL


def test_a_declared_class_reads_back_as_the_class_the_resolver_uses() -> None:
    for metadata in gated_tools():
        assert risk_class_of(metadata.risk_class) is RiskClass(metadata.risk_class)
