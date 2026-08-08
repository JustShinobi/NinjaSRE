"""Turning what a source reported into what the estate stores.

Four cases, and each of them is one an operator would notice getting wrong.

**The ordinary case.** A source reports something it has reported before. The
identity derives to the same key, so it is an update — a rename, a resize, a new
attribute — and never a second row.

**Two sources, one thing.** A hypervisor and a container runtime both describe
the same machine. They agree on a correlation key, so the second one finds the
first's record and adds its own contribution beside it rather than creating a
twin. Both sources are named on the resource afterwards, which is what makes
"where did this come from" answerable.

**A changed parent.** A guest migrated between nodes. The resource is the same
resource; only its parent moved. So the record updates and the graph edge is
rewritten — the old ``hosted_on`` edge is removed rather than left, because a
node-returning traversal cannot tell a retired edge from a live one.

**A reused identifier.** A provider deleted guest 101 and later created a new
guest that also got 101. The estate's stored resource is *absent*, so this is
not a resurrection: the retired record keeps its identity and its history, and
the newcomer gets a fresh one. The alternative — reusing the row — would give a
brand-new machine somebody else's outage history, which is worse than a
duplicate because it looks correct.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from platform.estate.attributes import screened
from platform.estate.discovery.port import DiscoveredResource
from platform.estate.identity import derive_resource_id
from platform.estate.kinds import KindRegistry
from platform.persistence.ports.estate_repository import (
    EstateRepository,
    Resource,
    ResourceSource,
)

#: Separates a derived key from the generation that reused it. Chosen because a
#: hex digest cannot contain it, so the split back is unambiguous and a
#: generation-suffixed key can never be mistaken for a first-generation one.
GENERATION_SEPARATOR: Final = "~"

#: How many times one provider identifier may be reused before the estate stops
#: making room for the next one. Reaching this means a provider is recycling
#: identifiers faster than anything can be reasoned about, and the honest
#: outcome is a loud failure rather than an unbounded family of records.
MAX_IDENTIFIER_GENERATIONS: Final[int] = 100


@dataclass(frozen=True, slots=True)
class Reconciled:
    """One discovered resource, as the estate will store it, and what it cost.

    ``dropped`` and ``invalid`` name attributes the kind did not declare or
    could not accept. They travel with the resource rather than being logged
    here because the sweep reports them once per sweep, and a warning per
    resource is a wall rather than a diagnosis.
    """

    resource: Resource
    dropped: tuple[str, ...] = ()
    invalid: tuple[str, ...] = ()
    screened: tuple[str, ...] = ()


async def identity_for(
    estate: EstateRepository,
    *,
    source: str,
    native_id: str,
) -> str:
    """Return the key this source's ``native_id`` should be stored under.

    Normally the derived key. When that key is already held by an *absent*
    resource, the next free generation of it — because a provider reusing an
    identifier after a deletion is describing a different thing, and giving it
    the retired machine's history would be a wrong answer that looks right.
    """
    base = derive_resource_id(source=source, native_id=native_id)
    for generation in range(1, MAX_IDENTIFIER_GENERATIONS + 1):
        candidate = base if generation == 1 else f"{base}{GENERATION_SEPARATOR}{generation}"
        stored = await estate.get(candidate)
        if stored is None or stored.absent_since is None:
            return candidate
    raise RuntimeError(
        f"{source} has reused the identifier {native_id!r} more than "
        f"{MAX_IDENTIFIER_GENERATIONS} times. Something is recycling identifiers faster "
        f"than the estate can describe, and storing another would hide it."
    )


async def reconcile(
    estate: EstateRepository,
    reported: DiscoveredResource,
    *,
    source: str,
    kinds: KindRegistry,
    parent_id: str | None,
    at: datetime,
) -> Reconciled:
    """Return ``reported`` as the resource the estate should store.

    Raises ``UnknownResourceKind`` for a kind nobody declared and
    ``NoStableIdentifier`` for a resource the source cannot name. Both are the
    caller's to catch: a sweep skips the offending resource and reports it,
    rather than abandoning every other resource the source got right.
    """
    kind = kinds.get(reported.kind)
    typed = kind.typed(reported.attributes)
    clean = screened(typed.values)

    existing = await _existing(estate, reported, source=source)
    resource_id = (
        existing.resource_id
        if existing is not None
        else await identity_for(estate, source=source, native_id=reported.native_id)
    )

    contribution = ResourceSource(
        integration=source,
        native_id=reported.native_id,
        display_name=reported.display_name,
        attributes=clean.values,
        observed_at=reported.observed_at or at,
    )

    return Reconciled(
        resource=Resource(
            resource_id=resource_id,
            kind=reported.kind,
            # The first source to describe a resource stays its primary one, so
            # a second integration arriving does not silently reassign every
            # resource in the estate to whichever swept most recently.
            source=existing.source if existing is not None else source,
            native_id=existing.native_id if existing is not None else reported.native_id,
            display_name=reported.display_name or (existing.display_name if existing else ""),
            correlation_key=reported.correlation_key
            or (existing.correlation_key if existing else ""),
            parent_id=parent_id,
            team_node_id=reported.team_node_id or (existing.team_node_id if existing else None),
            attributes=clean.values,
            labels=reported.labels or (existing.labels if existing else ()),
            sources=_attributed(existing, contribution),
            first_seen_at=existing.first_seen_at if existing is not None else at,
            # The sweep's instant, never the provider's. ``last_seen_at`` means
            # "when this deployment last saw it reported", which is a fact about
            # us; the provider's own reading time is on the contribution above,
            # where it belongs. Taking the provider's here makes absence depend
            # on clock skew between the deployment and the source — and a source
            # whose clock runs slow would have a resumed sweep decommission
            # everything an earlier pass ingested.
            last_seen_at=at,
        ),
        dropped=typed.dropped,
        invalid=typed.invalid,
        screened=clean.screened,
    )


async def _existing(
    estate: EstateRepository,
    reported: DiscoveredResource,
    *,
    source: str,
) -> Resource | None:
    """Return the stored resource ``reported`` describes, or ``None``.

    Correlation first, then this source's own view. The order matters: a second
    integration arriving with a correlation key must find the first's record
    *before* it derives an identity of its own, or it will have created the
    duplicate the correlation key exists to prevent.
    """
    if reported.correlation_key:
        correlated = await estate.by_correlation_key(
            kind=reported.kind, correlation_key=reported.correlation_key
        )
        if correlated is not None:
            return correlated
    return await estate.by_native_id(source=source, native_id=reported.native_id)


def _attributed(
    existing: Resource | None, contribution: ResourceSource
) -> tuple[ResourceSource, ...]:
    """Return every source's contribution, this one replacing its own earlier view."""
    kept = tuple(
        entry
        for entry in (existing.sources if existing is not None else ())
        if entry.integration != contribution.integration
    )
    return (*kept, contribution)


__all__ = [
    "GENERATION_SEPARATOR",
    "MAX_IDENTIFIER_GENERATIONS",
    "Reconciled",
    "identity_for",
    "reconcile",
]
