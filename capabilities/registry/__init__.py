"""The catalogue: discovery, validation, resolution, scoring, and selection.

Tier 2. The framework primitives are in ``core.capability``; what lives here is
everything that needs to *walk the repository* — which is why it sits above the
packages it inspects rather than beside them.

The pipeline runs one way, and each stage narrows the last:

    discovery  → every declaration in the repository
    validation → the same set, or a build failure naming what is wrong
    Registry   → the validated catalogue, built once and cached
    resolution → what one team has actually configured, with the exclusions
    scoring    → the same set, ranked against one incident
    selection  → what fits in a turn, plus the reason for every part of it

Nothing downstream of validation can encounter a broken declaration, because
validation does not return a partial catalogue. A dangling skill-to-tool
reference found at runtime is an incident during an incident.

    from capabilities.registry import build_registry, resolve_for, select

    catalogue = resolve_for(build_registry(), team_integrations)
    turn = select(catalogue, incident)
"""

from __future__ import annotations

from capabilities.registry.catalogue import (
    CatalogueError,
    Registry,
    ResolvedCatalogue,
    build_registry,
    registry_from,
    reset_registry_cache,
    resolve_for,
)
from capabilities.registry.disclosure import (
    DiscoveredSkill,
    SkillManifestError,
    body_violations,
    load_skill,
    parse_skill_manifest,
)
from capabilities.registry.discovery import DiscoveredCatalogue, DiscoveryError, discover
from capabilities.registry.planning import CatalogueRanker, TeamCatalogueResolver
from capabilities.registry.scoring import Incident, ScoredCapability, rank, score_capability
from capabilities.registry.selection import (
    SelectionError,
    SelectionResult,
    is_secondary,
    select,
    selection_record,
)
from capabilities.registry.validation import (
    ValidationError,
    ValidationFailure,
    failures,
    rules,
    validate,
)

__all__ = [
    "CatalogueError",
    "CatalogueRanker",
    "DiscoveredCatalogue",
    "DiscoveredSkill",
    "DiscoveryError",
    "Incident",
    "Registry",
    "ResolvedCatalogue",
    "ScoredCapability",
    "SelectionError",
    "SelectionResult",
    "SkillManifestError",
    "TeamCatalogueResolver",
    "ValidationError",
    "ValidationFailure",
    "body_violations",
    "build_registry",
    "discover",
    "failures",
    "is_secondary",
    "load_skill",
    "parse_skill_manifest",
    "rank",
    "registry_from",
    "reset_registry_cache",
    "resolve_for",
    "rules",
    "score_capability",
    "select",
    "selection_record",
    "validate",
]
