"""Finding every capability in the repository without a list of them anywhere.

A central registry file is a merge conflict on every integration and a line
somebody eventually forgets — and a capability that exists but was never
registered fails in the most expensive way available, by being absent from an
investigation that needed it while everything reports healthy.

So there is no list. Discovery walks three roots and takes what it finds:

* ``capabilities/tools/`` — the cross-vendor tools,
* ``capabilities/skills/`` — every directory holding a ``SKILL.md``,
* ``integrations/<vendor>/tools/`` — each vendor's own package.

Adding a capability is therefore creating one package, and nothing else.

Two decisions here are load-bearing. **An import failure is fatal**, named by
module: a catalogue quietly missing a vendor because its module raised on
import is exactly the silent absence this design exists to prevent. And
**duplicates are collected rather than resolved** — discovery reports what it
found, including two tools with one name, so validation can fail naming both
sources. Deduplicating here would pick a winner, and the loser would be a tool
whose author is certain it shipped.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from types import ModuleType

from capabilities.registry.disclosure import DiscoveredSkill, SkillManifestError, load_skill
from config.constants.capabilities import (
    CAPABILITY_TOOLS_PACKAGE,
    INSTALLED_CATALOGUE_CACHE_TTL_SECONDS,
    INTEGRATION_TOOLS_SUBPACKAGE,
    SKILL_MANIFEST_FILENAME,
    SKILL_TEMPLATE_DIRECTORY,
)
from core.capability.registered import RegisteredTool, capability_marker
from core.capability.tokens import TokenCounter, estimate_tokens

_INTEGRATIONS_PACKAGE = "integrations"


class DiscoveryError(Exception):
    """A root could not be walked, or a module in one could not be imported."""


@dataclass(frozen=True, slots=True)
class DiscoveredCatalogue:
    """Everything discovery found, before anything has been checked.

    May contain duplicate names and dangling references. That is the point:
    validation cannot report a duplicate it never saw.
    """

    tools: tuple[RegisteredTool, ...] = ()
    skills: tuple[DiscoveredSkill, ...] = ()
    scanned_packages: tuple[str, ...] = ()
    scanned_skill_roots: tuple[Path, ...] = ()

    def __len__(self) -> int:
        """Return how many capabilities of both kinds were found."""
        return len(self.tools) + len(self.skills)


def _import(name: str) -> ModuleType | None:
    """Return the module ``name``, or ``None`` when it simply does not exist.

    A missing package is legitimate — not every vendor ships tools, and the
    cross-vendor packages are empty before anything is written. A package that
    exists and *raises* is not, and is re-raised naming the module.
    """
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as error:
        if error.name == name or (error.name and name.startswith(f"{error.name}.")):
            return None
        raise DiscoveryError(
            f"{name}: could not be imported because {error.name!r} is missing"
        ) from error
    except Exception as error:
        raise DiscoveryError(f"{name}: failed to import: {error}") from error


def _tools_in(module: ModuleType) -> list[RegisteredTool]:
    """Return the declarations attached to ``module``'s own attributes.

    Only names the module itself binds are considered, and each registration is
    matched back to the module it was declared in. Without that, a tool
    imported for re-export would be discovered twice and collide with itself.
    """
    found: list[RegisteredTool] = []

    for attribute in vars(module).values():
        registered = capability_marker(attribute)
        if registered is not None and registered.source_module == module.__name__:
            found.append(registered)

    return found


def _walk_package(name: str) -> list[RegisteredTool]:
    """Return every tool declared in ``name`` or any module below it."""
    package = _import(name)
    if package is None:
        return []

    found = _tools_in(package)

    package_path = getattr(package, "__path__", None)
    if package_path is None:
        return found

    for module_info in pkgutil.walk_packages(package_path, prefix=f"{name}."):
        module = _import(module_info.name)
        if module is not None:
            found.extend(_tools_in(module))

    return found


def integration_tool_packages() -> tuple[str, ...]:
    """Return the ``tools`` subpackage of every installed integration."""
    package = _import(_INTEGRATIONS_PACKAGE)
    package_path = getattr(package, "__path__", None) if package else None
    if package_path is None:
        return ()

    return tuple(
        f"{_INTEGRATIONS_PACKAGE}.{found.name}.{INTEGRATION_TOOLS_SUBPACKAGE}"
        for found in pkgutil.iter_modules(package_path)
        if found.ispkg
    )


def default_skill_root() -> Path:
    """Return the directory the shipped skills live in."""
    package = importlib.import_module("capabilities")
    location = getattr(package, "__file__", None)
    if location is None:
        raise DiscoveryError("capabilities package has no filesystem location to walk")
    return Path(location).parent / "skills"


def discover_skills(
    roots: Iterable[Path | str],
    *,
    counter: TokenCounter = estimate_tokens,
) -> list[DiscoveredSkill]:
    """Return every skill under ``roots``, sorted by name.

    Roots are coerced rather than required to be ``Path`` already: they reach
    this from a deployment's configuration as often as from code, and a string
    that arrives there fails with an attribute error several frames down rather
    than with anything a reader could act on.

    Templates are skipped. They are text for a scaffold to copy and are
    deliberately incomplete; a template in the catalogue is an entry the model
    can select and learn nothing from.
    """
    found: list[DiscoveredSkill] = []

    for entry in roots:
        root = Path(entry)
        if not root.is_dir():
            continue
        for manifest in sorted(root.rglob(SKILL_MANIFEST_FILENAME)):
            if SKILL_TEMPLATE_DIRECTORY in manifest.parts:
                continue
            try:
                found.append(load_skill(manifest, counter=counter))
            except SkillManifestError as error:
                raise DiscoveryError(str(error)) from error

    return sorted(found, key=lambda skill: skill.name)


def discover(
    *,
    tool_packages: Sequence[str] | None = None,
    skill_roots: Sequence[Path | str] | None = None,
    counter: TokenCounter = estimate_tokens,
) -> DiscoveredCatalogue:
    """Return every capability declared in the repository.

    The roots are arguments so a test can point discovery at a fixture tree.
    Left out, they are the real ones — which is what makes "adding a capability
    edits no existing file" true rather than aspirational.
    """
    # The real tree is walked once and reused for a short window. The walk is
    # sixteen thousand modules through ``pkgutil`` plus every skill manifest
    # parsed from disk, and a console render asks for it more than once. A
    # caller naming its own roots is asking about a different tree and is
    # always answered from that tree.
    real_tree = tool_packages is None and skill_roots is None and counter is estimate_tokens
    if real_tree and _remembered is not None and monotonic() < _remembered[0]:
        return _remembered[1]

    packages = (
        tuple(tool_packages)
        if tool_packages is not None
        else (CAPABILITY_TOOLS_PACKAGE, *integration_tool_packages())
    )
    roots = (
        tuple(Path(root) for root in skill_roots)
        if skill_roots is not None
        else (default_skill_root(),)
    )

    tools: list[RegisteredTool] = []
    for package in packages:
        tools.extend(_walk_package(package))

    found = DiscoveredCatalogue(
        tools=tuple(sorted(tools, key=lambda found: (found.name, found.source))),
        skills=tuple(discover_skills(roots, counter=counter)),
        scanned_packages=packages,
        scanned_skill_roots=roots,
    )
    if real_tree:
        _remember(found)
    return found


#: The last walk of the real tree, and until when it may be reused.
_remembered: tuple[float, DiscoveredCatalogue] | None = None


def _remember(found: DiscoveredCatalogue) -> None:
    global _remembered  # noqa: PLW0603 — one process-wide memo, by design
    _remembered = (monotonic() + INSTALLED_CATALOGUE_CACHE_TTL_SECONDS, found)


def forget_discovered() -> None:
    """Drop the remembered walk, so the next ``discover()`` walks the real tree again.

    For a test that installs a capability and wants it seen at once. A running
    deployment never needs this: the window is a few seconds.
    """
    global _remembered  # noqa: PLW0603 — the same memo, being emptied
    _remembered = None


__all__ = [
    "forget_discovered",
    "DiscoveredCatalogue",
    "DiscoveryError",
    "default_skill_root",
    "discover",
    "discover_skills",
    "integration_tool_packages",
]
