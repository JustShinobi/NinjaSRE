"""Joining a change to the resource that broke, through the resource.

Correlating by time is the obvious thing and it is wrong. Any busy window holds
several changes, and a report that names one of them as the cause because it
landed thirteen minutes earlier has picked one at random and dressed it as
evidence. The correlation here runs a chain instead:

    a path a change touched
      → the component that owns that directory
        → the machines that component's own state says it manages
          → the resource under investigation

Every hop can fail, and where it fails decides the strength. A change whose
component built this machine is a governing change. A change to declarative
policy that names this machine's network is a plausible one — the firewall
profile a workload shares with everything else on its zone is genuinely a way to
break it, and genuinely not the same as altering the component that owns it. A
change that reached neither is in the same window and nothing more.

**The strength is a property of the pair, not of the change.** The same firewall
apply is a strong lead for a connectivity alert on the workload behind it and
nothing at all for a disk that filled up on another network. An engine that
graded changes rather than pairs would give both the same answer, which is
exactly the false positive this module exists to avoid.

Everything here is pure. What each component manages is read once, out of the
apply record, and handed in; the estate is read once, and handed in. That is
what makes the rule testable against a fixture instead of against a database,
and it is why the same function serves the capability, the report and the
console panel without any of them re-deriving it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any

from config.constants.changes import COMPONENT_PATH_ROOTS, SHARED_POLICY_ROOT
from config.prompts.changes import (
    CHANGE_MANAGES_RESOURCE,
    CHANGE_PATHS_UNAVAILABLE,
    CHANGE_TOUCHES_SHARED_POLICY,
    CHANGE_WINDOW_ONLY,
)
from platform.changes.models import Change


class CorrelationStrength(StrEnum):
    """How far along the chain from a change to a resource this link got.

    A closed set of three, ordered. The ordering is used — a report shows the
    strongest first — and it is why this is an enumeration rather than a score:
    a number invites a threshold, and a threshold is where "0.6 is probably the
    cause" comes from.
    """

    MANAGES_RESOURCE = "manages_resource"
    TOUCHES_SHARED_POLICY = "touches_shared_policy"
    WINDOW_ONLY = "window_only"

    @property
    def rank(self) -> int:
        """Return the sort order, strongest first."""
        return _RANKS[self]

    @property
    def is_temporal_only(self) -> bool:
        """Return whether this link is nothing but a shared window."""
        return self is CorrelationStrength.WINDOW_ONLY


_RANKS: Mapping[CorrelationStrength, int] = {
    CorrelationStrength.MANAGES_RESOURCE: 0,
    CorrelationStrength.TOUCHES_SHARED_POLICY: 1,
    CorrelationStrength.WINDOW_ONLY: 2,
}


@dataclass(frozen=True, slots=True)
class ResourceView:
    """The resource under investigation, reduced to what correlation needs.

    A view rather than the estate's own record, so this module depends on four
    strings instead of on the storage port — which is what lets the whole rule
    be exercised against a fixture, and what stops a console panel and a
    capability deriving the same correlation two different ways.
    """

    resource_id: str
    correlation_key: str = ""
    display_name: str = ""
    zone: str = ""
    domain: str = ""
    kind: str = ""

    def names(self) -> frozenset[str]:
        """Return the names a shared policy file could be about, lowercased.

        The zone is in here because a firewall profile is written per network
        far more often than per machine, and a change to the profile every guest
        on a network shares is a real way to break one of them.
        """
        found = {
            self.display_name,
            self.zone,
            self.domain,
            # The provider-native tail of the correlation key: for a hypervisor
            # guest that is its VMID, which is what a per-guest policy file is
            # named after.
            self.correlation_key.rsplit("/", 1)[-1] if self.correlation_key else "",
        }
        return frozenset(name.strip().lower() for name in found if name.strip())


@dataclass(frozen=True, slots=True)
class ComponentMap:
    """What each component's own state says it manages, by correlation key.

    The half of the chain a repository layout cannot answer. A directory name
    says which component owns a file; only the component's state says which
    machines that component built.
    """

    managed: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def components(self) -> frozenset[str]:
        """Return every component name this cluster declares."""
        return frozenset(self.managed)

    def manages(self, component: str, resource: ResourceView) -> bool:
        """Return whether ``component`` built the machine ``resource`` describes."""
        if not component or not resource.correlation_key:
            return False
        return resource.correlation_key in self.managed.get(component, ())

    def managing(self, resource: ResourceView) -> tuple[str, ...]:
        """Return the components that manage ``resource``, in name order."""
        return tuple(sorted(name for name in self.managed if self.manages(name, resource)))


@dataclass(frozen=True, slots=True)
class CorrelatedChange:
    """One change, one resource, and what actually connects them.

    ``chain`` is the evidence. A verdict without it is a claim, and the whole
    reason this feature exists is that "there was a deploy" and "the component
    that manages this container was applied" are different statements.
    """

    change: Change
    strength: CorrelationStrength
    why: str
    component: str = ""
    matched_path: str = ""
    matched_name: str = ""
    #: Path, component, resource key — the hops that were actually traversed.
    #: Empty for a link that traversed none.
    chain: tuple[str, ...] = ()

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form a trace, a route and a console read."""
        return {
            **self.change.to_record(),
            "strength": self.strength.value,
            "temporal_only": self.strength.is_temporal_only,
            "why": self.why,
            "correlated_component": self.component,
            "matched_path": self.matched_path,
            "matched_name": self.matched_name,
            "chain": list(self.chain),
        }


def component_for(path: str, components: Iterable[str]) -> str:
    """Return the component a repository path belongs to, or the empty string.

    Driven by the components the cluster declares rather than by a hard-coded
    layout. A path whose directory names a component nobody has resolves to no
    component at all: guessing one is how a correlation gets invented, and an
    invented component is one hop from an invented cause.
    """
    known = set(components)
    if not known:
        return ""
    parts = [part for part in PurePosixPath(path).parts if part not in {"/", "."}]
    for index, part in enumerate(parts):
        if index > 1:
            # Only the first two segments are considered. Deeper than that and
            # the match is a file that happens to share a component's name.
            break
        if index == 1 and parts[0] not in COMPONENT_PATH_ROOTS:
            break
        if part in known:
            return part
    return ""


def correlate(
    change: Change,
    *,
    resource: ResourceView,
    components: ComponentMap,
) -> CorrelatedChange:
    """Return ``change`` graded against ``resource``, with the chain it travelled."""
    governing = _governing(change, resource=resource, components=components)
    if governing is not None:
        component, path = governing
        return CorrelatedChange(
            change=change,
            strength=CorrelationStrength.MANAGES_RESOURCE,
            why=CHANGE_MANAGES_RESOURCE.format(path=path, component=component),
            component=component,
            matched_path=path,
            chain=(path, component, resource.correlation_key),
        )

    shared = _shared_policy(change, resource=resource)
    if shared is not None:
        path, matched = shared
        return CorrelatedChange(
            change=change,
            strength=CorrelationStrength.TOUCHES_SHARED_POLICY,
            why=CHANGE_TOUCHES_SHARED_POLICY.format(path=path, matched=matched),
            component=change.component,
            matched_path=path,
            matched_name=matched,
            chain=(path, matched, resource.correlation_key),
        )

    # Nothing connects them. Said as a coincidence in words, because a reader
    # shown a label alone concludes "a change correlated with the incident".
    unavailable = CHANGE_PATHS_UNAVAILABLE if not change.paths and "paths" in change.detail else ""
    return CorrelatedChange(
        change=change,
        strength=CorrelationStrength.WINDOW_ONLY,
        why=f"{CHANGE_WINDOW_ONLY}{unavailable}",
        component=change.component,
    )


def correlate_all(
    changes: Iterable[Change],
    *,
    resource: ResourceView,
    components: ComponentMap,
) -> tuple[CorrelatedChange, ...]:
    """Return every change graded, strongest first, then applied, then newest.

    The ordering is the reading order. An apply that governs the resource is
    what somebody wants at the top; a commit nobody deployed never outranks an
    apply of the same strength, because it did not change the cluster.
    """
    found = [correlate(change, resource=resource, components=components) for change in changes]
    found.sort(
        key=lambda entry: (
            entry.strength.rank,
            not entry.change.applied,
            -entry.change.instant.timestamp(),
            entry.change.change_id,
        )
    )
    return tuple(found)


# --- the hops -----------------------------------------------------------------


def _governing(
    change: Change,
    *,
    resource: ResourceView,
    components: ComponentMap,
) -> tuple[str, str] | None:
    """Return the (component, path) that governs ``resource``, or ``None``.

    The change's own declared component is checked first and is authoritative:
    an apply record says which component was applied, and no path rule can be
    more certain than that. The paths are then checked, which is what serves a
    source that reports paths without a component.
    """
    if components.manages(change.component, resource):
        path = next(
            (
                touched
                for touched in change.paths
                if component_for(touched, components.components) == change.component
            ),
            "",
        )
        return change.component, path or f"the {change.component} component"

    for path in change.paths:
        component = component_for(path, components.components)
        if component and components.manages(component, resource):
            return component, path
    return None


def _shared_policy(change: Change, *, resource: ResourceView) -> tuple[str, str] | None:
    """Return the (path, name) of a shared policy naming ``resource``, or ``None``.

    Matched on the path alone. Reading the file's contents would be a second
    ingestion of the repository and, worse, would put this module in the
    business of judging what a change *said* — which is out of scope on purpose:
    the correlation is about what and when, never about merit.
    """
    names = resource.names()
    if not names:
        return None

    for path in change.paths:
        parts = PurePosixPath(path).parts
        if not parts or parts[0] != SHARED_POLICY_ROOT:
            continue
        for segment in (*parts[1:-1], PurePosixPath(path).stem):
            if segment.lower() in names:
                return path, segment
    return None


def views_of(resources: Sequence[Any]) -> tuple[ResourceView, ...]:
    """Return estate resources as the views correlation reads.

    Takes whatever carries the five attributes rather than the estate's own
    record, so this module stays free of the storage port and the console's
    fixture plane can build one from a dictionary.
    """
    return tuple(
        ResourceView(
            resource_id=str(getattr(resource, "resource_id", "")),
            correlation_key=str(getattr(resource, "correlation_key", "")),
            display_name=str(getattr(resource, "display_name", "")),
            zone=str(dict(getattr(resource, "attributes", {})).get("zone", "")),
            domain=str(dict(getattr(resource, "attributes", {})).get("domain", "")),
            kind=str(getattr(resource, "kind", "")),
        )
        for resource in resources
    )


__all__ = [
    "ComponentMap",
    "CorrelatedChange",
    "CorrelationStrength",
    "ResourceView",
    "component_for",
    "correlate",
    "correlate_all",
    "views_of",
]
