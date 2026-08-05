"""The read side of the catalogue, for the console and for generated documentation.

Both callers want the same thing and neither should reach into the registry to
get it. The console renders a catalogue page; the documentation generator
renders a reference page; and if each walked ``Registry`` itself, the two would
drift until an operator's screen and the published reference disagreed about
what a tool does.

So one view type, built once, serialisable, and carrying the two facts an
operator actually needs that the declaration alone does not give them:
**whether this team can run it**, and **what is missing if not**. A catalogue
page that lists everything the repository ships is a catalogue page that lies
to two thirds of its readers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from capabilities.registry.catalogue import Registry, ResolvedCatalogue
from core.capability.metadata import (
    CapabilityKind,
    CapabilityMetadata,
    SkillMetadata,
    ToolMetadata,
)
from core.capability.ports import IntegrationAvailability


@dataclass(frozen=True, slots=True)
class CapabilityView:
    """One catalogue entry as a reader sees it."""

    name: str
    kind: CapabilityKind
    display_name: str
    description: str
    domain: str
    tags: tuple[str, ...]
    use_cases: tuple[str, ...]
    anti_examples: tuple[str, ...]
    requires: tuple[str, ...]
    available: bool
    unmet: tuple[str, ...] = ()

    # Tools only.
    evidence_source: str = ""
    evidence_type: str = ""
    side_effect_level: str = ""
    parallel_safe: bool = False
    requires_approval: bool = False
    approval_reason: str = ""
    input_schema: Mapping[str, Any] | None = None

    # Skills only.
    directs_tools: tuple[str, ...] = ()
    alert_sources: tuple[str, ...] = ()

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this entry."""
        record: dict[str, Any] = {
            "name": self.name,
            "kind": self.kind.value,
            "display_name": self.display_name,
            "description": self.description,
            "domain": self.domain,
            "tags": list(self.tags),
            "use_cases": list(self.use_cases),
            "anti_examples": list(self.anti_examples),
            "requires": list(self.requires),
            "available": self.available,
            "unmet": list(self.unmet),
        }
        if self.kind is CapabilityKind.TOOL:
            record.update(
                {
                    "evidence_source": self.evidence_source,
                    "evidence_type": self.evidence_type,
                    "side_effect_level": self.side_effect_level,
                    "parallel_safe": self.parallel_safe,
                    "requires_approval": self.requires_approval,
                    "approval_reason": self.approval_reason,
                    "input_schema": dict(self.input_schema or {}),
                }
            )
        else:
            record.update(
                {
                    "directs_tools": list(self.directs_tools),
                    "alert_sources": list(self.alert_sources),
                }
            )
        return record


def _view(
    metadata: CapabilityMetadata,
    *,
    available: bool,
    unmet: tuple[str, ...],
    input_schema: Mapping[str, Any] | None = None,
) -> CapabilityView:
    """Return the view for one declaration."""
    view = CapabilityView(
        name=metadata.name,
        kind=metadata.kind,
        display_name=metadata.display_name,
        description=metadata.description,
        domain=metadata.domain,
        tags=metadata.tags,
        use_cases=metadata.use_cases,
        anti_examples=metadata.anti_examples,
        requires=metadata.requires.names(),
        available=available,
        unmet=unmet,
    )

    if isinstance(metadata, ToolMetadata):
        return replace(
            view,
            evidence_source=metadata.evidence_source,
            evidence_type=metadata.evidence_type.value,
            side_effect_level=metadata.side_effect_level.value,
            parallel_safe=metadata.parallel_safe,
            requires_approval=metadata.requires_approval,
            approval_reason=metadata.approval_reason,
            input_schema=input_schema,
        )

    if isinstance(metadata, SkillMetadata):
        return replace(
            view,
            directs_tools=metadata.directs_tools,
            alert_sources=metadata.applies_when.alert_sources,
        )

    return view


def catalogue_view(
    registry: Registry,
    availability: IntegrationAvailability | None = None,
) -> tuple[CapabilityView, ...]:
    """Return every capability, tools then skills, each in name order.

    Without ``availability`` everything reads as available, which is the right
    answer for generated documentation: the reference describes what the
    software ships, not what one deployment configured.
    """
    views: list[CapabilityView] = []

    for name in sorted(registry.tools):
        found = registry.tools[name]
        unmet = availability.unmet(found.metadata.requires) if availability else ()
        views.append(
            _view(
                found.metadata,
                available=not unmet,
                unmet=unmet,
                input_schema=found.input_schema,
            )
        )

    for name in sorted(registry.skills):
        skill = registry.skills[name]
        unmet = availability.unmet(skill.metadata.requires) if availability else ()
        views.append(_view(skill.metadata, available=not unmet, unmet=unmet))

    return tuple(views)


def resolved_view(registry: Registry, catalogue: ResolvedCatalogue) -> tuple[CapabilityView, ...]:
    """Return every capability, with the exclusions a resolution already computed."""
    excluded = {entry.name: entry.unmet for entry in catalogue.excluded}
    views: list[CapabilityView] = []

    for name in sorted(registry.tools):
        found = registry.tools[name]
        unmet = excluded.get(name, ())
        views.append(
            _view(
                found.metadata,
                available=name not in excluded,
                unmet=unmet,
                input_schema=found.input_schema,
            )
        )

    for name in sorted(registry.skills):
        skill = registry.skills[name]
        views.append(
            _view(
                skill.metadata,
                available=name not in excluded,
                unmet=excluded.get(name, ()),
            )
        )

    return tuple(views)


def find(views: Sequence[CapabilityView], name: str) -> CapabilityView | None:
    """Return the view called ``name``, or ``None``."""
    for view in views:
        if view.name == name:
            return view
    return None


def as_records(views: Sequence[CapabilityView]) -> list[dict[str, Any]]:
    """Return the views as JSON-serialisable records."""
    return [view.to_record() for view in views]


def summary(views: Sequence[CapabilityView]) -> dict[str, int]:
    """Return the counts a catalogue page leads with."""
    return {
        "tools": sum(1 for view in views if view.kind is CapabilityKind.TOOL),
        "skills": sum(1 for view in views if view.kind is CapabilityKind.SKILL),
        "available": sum(1 for view in views if view.available),
        "excluded": sum(1 for view in views if not view.available),
        "approval_gated": sum(1 for view in views if view.requires_approval),
    }


__all__ = [
    "CapabilityView",
    "as_records",
    "catalogue_view",
    "find",
    "resolved_view",
    "summary",
]
