"""The validated catalogue, and the narrower one a particular team actually has.

Two types, because they answer two different questions. ``Registry`` is what
the repository declares — built once, validated, and shared. ``ResolvedCatalogue``
is what one team can run, which is smaller and different for every team, and
carries the record of what was left out.

That record is the part worth arguing for. A capability missing from a team's
catalogue looks identical whether it was never written or is simply not
configured — and only one of those is something an operator can fix in a
minute. So exclusions are values with reasons attached rather than an absence,
and the console can show "Datadog tools: 14 available, 6 excluded (no Splunk
integration)" instead of showing nothing at all.

The registry is cached because building it imports every capability package in
the repository, and doing that per investigation would put a package walk on
the incident path.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from capabilities.registry.disclosure import DiscoveredSkill
from capabilities.registry.discovery import DiscoveredCatalogue, discover
from capabilities.registry.validation import validate
from core.capability.metadata import (
    CapabilityKind,
    CapabilityMetadata,
    ExcludedCapability,
)
from core.capability.ports import IntegrationAvailability
from core.capability.registered import RegisteredTool
from core.capability.tokens import TokenCounter, estimate_tokens


class CatalogueError(Exception):
    """The catalogue could not be built or resolved."""


@dataclass(frozen=True, slots=True)
class Registry:
    """Every capability the repository declares, already validated.

    Nothing here can be broken. ``build_registry`` is the only way to obtain
    one and it validates before constructing, so a caller holding a ``Registry``
    is holding a catalogue whose skill-to-tool references all resolve.
    """

    tools: Mapping[str, RegisteredTool] = field(default_factory=dict)
    skills: Mapping[str, DiscoveredSkill] = field(default_factory=dict)

    def tool(self, name: str) -> RegisteredTool | None:
        """Return the tool called ``name``, or ``None``."""
        return self.tools.get(name)

    def skill(self, name: str) -> DiscoveredSkill | None:
        """Return the skill called ``name``, or ``None``."""
        return self.skills.get(name)

    def metadata(self) -> tuple[CapabilityMetadata, ...]:
        """Return every declaration, tools then skills, each in name order."""
        return tuple(
            [self.tools[name].metadata for name in sorted(self.tools)]
            + [self.skills[name].metadata for name in sorted(self.skills)]
        )

    def __len__(self) -> int:
        """Return how many capabilities of both kinds are registered."""
        return len(self.tools) + len(self.skills)


@dataclass(frozen=True, slots=True)
class ResolvedCatalogue:
    """What one team can actually run, and what it cannot, with reasons."""

    tools: tuple[RegisteredTool, ...] = ()
    skills: tuple[DiscoveredSkill, ...] = ()
    excluded: tuple[ExcludedCapability, ...] = ()

    def metadata(self) -> tuple[CapabilityMetadata, ...]:
        """Return every available declaration, tools then skills."""
        return tuple([found.metadata for found in self.tools] + [s.metadata for s in self.skills])

    def tool(self, name: str) -> RegisteredTool | None:
        """Return the available tool called ``name``, or ``None``."""
        for found in self.tools:
            if found.name == name:
                return found
        return None

    def exclusion(self, name: str) -> ExcludedCapability | None:
        """Return why ``name`` is unavailable to this team, if it is."""
        for excluded in self.excluded:
            if excluded.name == name:
                return excluded
        return None

    def __len__(self) -> int:
        """Return how many capabilities of both kinds this team can run."""
        return len(self.tools) + len(self.skills)


def registry_from(catalogue: DiscoveredCatalogue) -> Registry:
    """Return the registry a validated discovery result describes."""
    return Registry(
        tools={found.name: found for found in catalogue.tools},
        skills={skill.name: skill for skill in catalogue.skills},
    )


#: The built registry, keyed by the roots it was built from. Building imports
#: every capability package in the repository; doing that per investigation
#: would put a package walk on the incident path.
_CACHE: dict[tuple[object, ...], Registry] = {}


def build_registry(
    *,
    tool_packages: Sequence[str] | None = None,
    skill_roots: Sequence[Path | str] | None = None,
    counter: TokenCounter = estimate_tokens,
    use_cache: bool = True,
) -> Registry:
    """Return the validated registry, building it the first time it is asked for.

    Validation happens before the registry exists rather than after, so there
    is no window in which a caller can hold a catalogue that has not passed the
    gate.
    """
    key: tuple[object, ...] = (
        tuple(tool_packages) if tool_packages is not None else None,
        tuple(str(root) for root in skill_roots) if skill_roots is not None else None,
    )

    if use_cache and key in _CACHE:
        return _CACHE[key]

    discovered = discover(tool_packages=tool_packages, skill_roots=skill_roots, counter=counter)
    registry = registry_from(validate(discovered, counter=counter))

    if use_cache:
        _CACHE[key] = registry
    return registry


def reset_registry_cache() -> None:
    """Forget the built registry. For tests that change what is discoverable."""
    _CACHE.clear()


def resolve_for(registry: Registry, availability: IntegrationAvailability) -> ResolvedCatalogue:
    """Return the part of ``registry`` this team has configured, with exclusions.

    A skill is also excluded when every tool it directs is — it would be
    selected, its body loaded into the turn, and it would name tools the model
    cannot call. A skill that directs nothing is methodology and always
    survives.
    """
    tools: list[RegisteredTool] = []
    skills: list[DiscoveredSkill] = []
    excluded: list[ExcludedCapability] = []

    for name in sorted(registry.tools):
        found = registry.tools[name]
        unmet = availability.unmet(found.metadata.requires)
        if unmet:
            excluded.append(ExcludedCapability(name=name, kind=CapabilityKind.TOOL, unmet=unmet))
        else:
            tools.append(found)

    available_tools = {found.name for found in tools}

    for name in sorted(registry.skills):
        skill = registry.skills[name]
        unmet = availability.unmet(skill.metadata.requires)
        directed = skill.metadata.directs_tools

        if not unmet and directed and not (set(directed) & available_tools):
            unmet = (
                tuple(
                    requirement
                    for tool_name in directed
                    for requirement in _requirements_of(registry, tool_name)
                )
                or directed
            )

        if unmet:
            excluded.append(
                ExcludedCapability(name=name, kind=CapabilityKind.SKILL, unmet=_unique(unmet))
            )
        else:
            skills.append(skill)

    return ResolvedCatalogue(tools=tuple(tools), skills=tuple(skills), excluded=tuple(excluded))


def _requirements_of(registry: Registry, tool_name: str) -> tuple[str, ...]:
    """Return what a tool needs, so an excluded skill can say what is missing."""
    found = registry.tools.get(tool_name)
    return found.metadata.requires.names() if found else ()


def _unique(names: Sequence[str]) -> tuple[str, ...]:
    """Return ``names`` deduplicated, order preserved."""
    seen: dict[str, None] = {}
    for name in names:
        seen.setdefault(name, None)
    return tuple(seen)


__all__ = [
    "CatalogueError",
    "Registry",
    "ResolvedCatalogue",
    "build_registry",
    "registry_from",
    "reset_registry_cache",
    "resolve_for",
]
