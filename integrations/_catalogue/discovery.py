"""Assembling the catalogue by walking, never by reading a list (FR-003).

``integrations/registry.py`` already walks the tree for descriptors — the
credential half. This walks it for the operational half: what class of system
each vendor is, what it can be asked to do, what permissions that needs, and
whether it ships everything it is required to.

The two walks are deliberately separate. The registry is what ``platform/``
composition needs at start-up and must stay cheap and dependency-free; this one
reads the filesystem and imports every vendor's tools, which is a build-time and
console-time cost rather than a start-up one.

**The roots are computed once, here, from the package's own location.** Parity
checks two directories outside ``integrations/`` — the skills and the synthetic
scenarios — and computing that path is a filesystem operation rather than an
import, so the tier boundary holds: nothing here imports ``capabilities``. That
is also why it is one function: a path expression repeated at three call sites
is three chances to check a directory that is not there and report success.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Final

import integrations
from config.constants.capabilities import INSTALLED_CATALOGUE_CACHE_TTL_SECONDS
from core.capability.registered import capability_marker
from integrations._catalogue.entry import (
    CatalogueEntry,
    HealthStatus,
    IntegrationProfile,
)
from integrations._catalogue.health import HealthLedger
from integrations._catalogue.validation import ParityReport, parity_of, validate_parity
from integrations.registry import descriptors, is_vendor_package
from platform.credentials.descriptor import IntegrationDescriptor

#: What a vendor package exposes for the operational half of the catalogue.
PROFILE_ATTRIBUTE: Final = "PROFILE"

#: The subpackage each vendor declares its agent-callable tools in.
TOOLS_SUBPACKAGE: Final = "tools"

#: Where the methodology skills live, relative to the repository root.
SKILL_ROOT_PARTS: Final[tuple[str, ...]] = ("capabilities", "skills")

#: Where the synthetic scenarios live, relative to the repository root. One
#: module per integration, named for it, which is what makes "at least one
#: scenario exercises this integration" a check rather than a search.
SCENARIO_ROOT_PARTS: Final[tuple[str, ...]] = ("tests", "synthetic", "integration_scenarios")


def package_root() -> Path:
    """Return the directory the vendor packages live in."""
    location = getattr(integrations, "__file__", None)
    if location is None:
        raise LookupError("the integrations package has no filesystem location to walk")
    return Path(location).parent


def repository_root() -> Path:
    """Return the checkout root the artefact directories hang off."""
    return package_root().parent


def skill_root() -> Path:
    """Return the directory holding the methodology skills."""
    return repository_root().joinpath(*SKILL_ROOT_PARTS)


def scenario_root() -> Path:
    """Return the directory holding the per-integration synthetic scenarios."""
    return repository_root().joinpath(*SCENARIO_ROOT_PARTS)


def vendor_packages() -> tuple[str, ...]:
    """Return every vendor package name under ``integrations/``, in name order."""
    return tuple(
        sorted(
            module.name
            for module in pkgutil.iter_modules([str(package_root())])
            if module.ispkg and is_vendor_package(module.name)
        )
    )


def profiles() -> dict[str, IntegrationProfile]:
    """Return every vendor's declared profile, keyed by name.

    An import failure is not swallowed, for the same reason it is not swallowed
    in the registry: a catalogue quietly missing the one vendor that mattered
    reports as a complete catalogue.
    """
    found: dict[str, IntegrationProfile] = {}
    for name in vendor_packages():
        package = importlib.import_module(f"{integrations.__name__}.{name}")
        profile = getattr(package, PROFILE_ATTRIBUTE, None)
        if profile is None:
            raise LookupError(
                f"the integration package {name!r} exposes no {PROFILE_ATTRIBUTE}, so nothing "
                f"knows what class of system it is, which permissions it needs, or where it "
                f"can be reached"
            )
        if not isinstance(profile, IntegrationProfile):
            raise TypeError(
                f"{name}.{PROFILE_ATTRIBUTE} is a {type(profile).__name__}, "
                f"not an IntegrationProfile"
            )
        found[profile.integration] = profile
    return found


def capabilities_of(integration: str) -> tuple[str, ...]:
    """Return the tools ``integration`` declares, in name order.

    Reads the declarations rather than the file names: a module in ``tools/``
    that declares nothing is not a capability, and counting it would let an
    integration reach parity on an empty file.
    """
    module_name = f"{integrations.__name__}.{integration}.{TOOLS_SUBPACKAGE}"
    try:
        package = importlib.import_module(module_name)
    except ModuleNotFoundError:
        return ()

    found: set[str] = set()
    package_path = getattr(package, "__path__", None)
    modules = [package]
    if package_path is not None:
        modules.extend(
            importlib.import_module(info.name)
            for info in pkgutil.walk_packages(package_path, prefix=f"{module_name}.")
        )
    for module in modules:
        for attribute in vars(module).values():
            registered = capability_marker(attribute)
            if registered is not None and registered.source_module == module.__name__:
                found.add(registered.name)
    return tuple(sorted(found))


def parity_reports() -> tuple[ParityReport, ...]:
    """Return one parity report per installed integration, in name order."""
    package = package_root()
    skills = skill_root()
    scenarios = scenario_root()
    return tuple(
        parity_of(name, package_root=package, skill_root=skills, scenario_root=scenarios)
        for name in vendor_packages()
    )


#: What ``health_detail`` reads for an integration nobody has connected, when
#: the caller can say so. Written once here rather than at every call site
#: that passes ``configured``, so the sentence cannot drift between them.
_UNCONFIGURED_DETAIL: Final = "no credential is stored for this node"


def catalogue(
    *,
    health: HealthLedger | None = None,
    configured: frozenset[str] | None = None,
) -> tuple[CatalogueEntry, ...]:
    """Return every installed integration as a catalogue entry, in name order.

    ``health`` is the ledger the scheduled live runs write to. Left out, every
    entry reports ``UNKNOWN``, which is the honest answer for a deployment that
    has not run one.

    ``configured`` is which integrations this tenant holds a live credential
    for, from the vault rather than the ledger. Left out — every existing
    caller before this parameter existed — the credential question is not
    asked and the ledger alone decides, exactly as before. Given, an
    integration outside the set reports ``UNCONFIGURED`` regardless of what
    the ledger says about it: a credential that was never written cannot have
    been checked, so there is nothing the ledger could hold that would be
    worth showing ahead of "nothing is connected here yet".
    """
    entries: list[CatalogueEntry] = []
    for installed in _installed():
        name = installed.name
        if configured is not None and name not in configured:
            resolved_health = HealthStatus.UNCONFIGURED
            resolved_detail = _UNCONFIGURED_DETAIL
        else:
            record = health.status_of(name) if health is not None else None
            resolved_health = record.status if record is not None else HealthStatus.UNKNOWN
            resolved_detail = record.detail if record is not None else ""
        entries.append(
            CatalogueEntry(
                name=name,
                profile=installed.profile,
                descriptor=installed.descriptor,
                parity=installed.parity,
                capabilities=installed.capabilities,
                health=resolved_health,
                health_detail=resolved_detail,
            )
        )
    return tuple(entries)


@dataclass(frozen=True, slots=True)
class _Installed:
    """What the walk finds about one vendor: everything but its health."""

    name: str
    profile: IntegrationProfile
    descriptor: IntegrationDescriptor
    parity: ParityReport
    capabilities: tuple[str, ...]


#: The last walk of the vendor packages, and until when it may be reused.
_remembered: tuple[float, tuple[_Installed, ...]] | None = None


def _installed() -> tuple[_Installed, ...]:
    """Return every installed vendor's shape, walking the packages once per window.

    The shape — which packages exist, their profiles, their parity, the tools
    they declare — cannot change while the process runs. The ledger's view of
    each one can, which is why health is applied by ``catalogue`` on every
    call and never remembered here.
    """
    global _remembered  # noqa: PLW0603 — one process-wide memo, by design
    if _remembered is not None and monotonic() < _remembered[0]:
        return _remembered[1]
    declared = descriptors()
    described = profiles()
    reports = {report.integration: report for report in parity_reports()}
    found = tuple(
        _Installed(
            name=name,
            profile=described[name],
            descriptor=_descriptor_for(name, declared),
            parity=reports[name],
            capabilities=capabilities_of(name),
        )
        for name in vendor_packages()
    )
    _remembered = (monotonic() + INSTALLED_CATALOGUE_CACHE_TTL_SECONDS, found)
    return found


def forget_installed() -> None:
    """Drop the remembered walk, so the next ``catalogue()`` walks the packages again."""
    global _remembered  # noqa: PLW0603 — the same memo, being emptied
    _remembered = None


def entry(
    name: str,
    *,
    health: HealthLedger | None = None,
    configured: frozenset[str] | None = None,
) -> CatalogueEntry:
    """Return one integration's catalogue entry.

    Raises:
        LookupError: no integration is installed under that name.
    """
    for found in catalogue(health=health, configured=configured):
        if found.name == name:
            return found
    raise LookupError(
        f"no integration named {name!r} is installed. Installed: "
        f"{', '.join(vendor_packages()) or 'none'}"
    )


def validate() -> tuple[CatalogueEntry, ...]:
    """Return the catalogue, or raise naming every integration that is incomplete.

    Returning the catalogue rather than ``None`` is so the only way to obtain a
    validated one is to have validated it — the same reasoning the capability
    registry's validator uses, and for the same reason: a function that returns
    nothing invites a caller who forgets to call it.
    """
    entries = catalogue()
    validate_parity(found.parity for found in entries)
    return entries


def _descriptor_for(name: str, declared: dict[str, IntegrationDescriptor]) -> IntegrationDescriptor:
    """Return ``name``'s descriptor, or say which declaration is missing."""
    found = declared.get(name)
    if found is None:
        raise LookupError(
            f"the integration package {name!r} declares a profile but no descriptor, so "
            f"nothing knows what its credential looks like or how the secret enters a request"
        )
    return found


__all__ = [
    "PROFILE_ATTRIBUTE",
    "SCENARIO_ROOT_PARTS",
    "SKILL_ROOT_PARTS",
    "TOOLS_SUBPACKAGE",
    "capabilities_of",
    "catalogue",
    "entry",
    "forget_installed",
    "package_root",
    "parity_reports",
    "profiles",
    "repository_root",
    "scenario_root",
    "skill_root",
    "validate",
    "vendor_packages",
]
