"""What the deployment knows about a resource that the provider cannot report.

A hypervisor knows a container exists, which node it is on, and whether it is
running. It does not know whether it matters. Criticality, tier, and the domain
a service answers on are decisions somebody made and wrote down, and they are
exactly the facts that turn "a container stopped" into "the container serving
the public site stopped".

**The direction of truth is enforced here rather than agreed to.** The live
source decides what exists; a declared file decides what a thing means. So
``apply_enrichment`` only ever *annotates* resources the estate already holds.
There is no path from a file to an ``upsert`` of something new, which is why an
inventory that still lists a machine deleted last April cannot resurrect it —
that entry becomes a divergence record instead, which is a finding rather than
an error.

**Divergence is content.** Three kinds, all stored and all returned: an entry
only in the file, a resource only in the provider, and a resource whose address
no declared network covers. Each of the three is somebody's afternoon if it is
found by hand six months late, and none of them is a failure of this process.

**Zones come from addresses.** ``ZoneMap`` is a total function from address to
zone name, built from declared networks, refusing an overlap at construction
because a map where one address has two zones has no correct answer. What it
does not do is guess: an address outside every declared network gets the empty
string and a divergence record, never the nearest network or a default.

This module is provider-neutral on purpose. The *shapes* — a zone map, an
annotation, a divergence — are the same whatever produced them, and the
file formats they were read out of belong to whichever integration published
them. A second estate brings its own ingestion and reuses everything here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from ipaddress import IPv4Network, ip_address, ip_network
from typing import Any, Final

from config.constants.estate import MAX_ESTATE_PAGE_SIZE
from platform.estate.attributes import AttributeType, screened, typed
from platform.estate.kinds import KindRegistry
from platform.observability.logging import get_logger
from platform.persistence.ports.estate_repository import EstateQuery, Resource, whole_estate
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope

logger = get_logger(__name__)

#: What an enrichment may write onto a resource, and nothing else. A closed set
#: for the same reason the kind registry is closed: a file that grew a field is
#: not a reason for the estate to grow a column nobody declared, and an
#: annotation nobody declared is one no query can filter on.
#:
#: All five are strings. ``criticality`` and ``tier`` are the operator's own
#: vocabulary rather than an enumeration this platform invents — a deployment
#: whose tiers are "gold/silver/bronze" and one whose tiers are "0/1/2" are both
#: describing the same thing, and refusing one of them would be this system
#: telling an operator how to name their own estate.
ANNOTATION_TYPES: Final[Mapping[str, AttributeType]] = {
    #: Where the packets go. Derived from the address, never from a name.
    "zone": AttributeType.STRING,
    "criticality": AttributeType.STRING,
    "tier": AttributeType.STRING,
    #: The name a request arrives on — the edge between "the site is down" and
    #: "this container is down".
    "domain": AttributeType.STRING,
    "owner": AttributeType.STRING,
}

#: The attribute an address is read from when a zone is derived. Written by the
#: integration that discovered the resource; named here because the derivation
#: is here and a caller should not have to know two spellings.
ADDRESS_ATTRIBUTE: Final = "address"

#: How a zone appears as a label, so ``/resources`` can group and filter by it
#: without a query language for attributes. One prefix, in one place, because a
#: label written two ways is two zones.
ZONE_LABEL_PREFIX: Final = "zone:"


class OverlappingZones(ValueError):
    """Two declared networks cover one address, so it has two zones.

    Refused at construction rather than resolved by most-specific-match. The
    longest-prefix rule is what a router does and it is a reasonable rule; it is
    not a rule an operator writing a zone file has agreed to, and silently
    applying it would place guests in a zone nobody wrote down.
    """

    def __init__(self, first: str, second: str) -> None:
        super().__init__(
            f"the declared networks {first} and {second} overlap, so an address in both has "
            f"two zones. A zone map with two answers has no correct one."
        )
        self.first = first
        self.second = second


@dataclass(frozen=True, slots=True)
class ZoneMap:
    """Declared networks, and the total function from address to zone name."""

    networks: tuple[tuple[IPv4Network, str], ...] = ()

    @classmethod
    def of(cls, declared: Mapping[str, str]) -> ZoneMap:
        """Return the map ``declared`` describes, refusing an overlap.

        Raises:
            ValueError: a key is not a network, or names a host inside one —
                ``10.20.30.1/24`` is an address with a prefix, not a network,
                and accepting it would silently mean ``10.20.30.0/24``.
            OverlappingZones: two networks cover one address.
        """
        parsed: list[tuple[IPv4Network, str]] = []
        for cidr, name in declared.items():
            network = ip_network(cidr, strict=True)
            if not isinstance(network, IPv4Network):
                raise ValueError(
                    f"{cidr} is not an IPv4 network. Zones are derived from IPv4 addresses "
                    f"because that is what a guest reports."
                )
            for existing, _ in parsed:
                if network.overlaps(existing):
                    raise OverlappingZones(str(existing), str(network))
            parsed.append((network, name))
        return cls(networks=tuple(parsed))

    def zone_for(self, address: str) -> str:
        """Return the zone ``address`` sits in, or ``""`` when none covers it.

        Total, and empty rather than a guess. Accepts a bare address or one
        carrying a prefix, because a hypervisor writes ``10.20.30.7/24`` in a
        guest's network line and the caller should not have to strip it.
        """
        candidate = address.strip().split("/", 1)[0]
        if not candidate:
            return ""
        try:
            parsed = ip_address(candidate)
        except ValueError:
            return ""
        for network, name in self.networks:
            if parsed in network:
                return name
        return ""


class DivergenceKind(StrEnum):
    """The three ways a declared inventory and a live source disagree."""

    #: Declared, and the provider does not report it. The machine is gone, and
    #: the file is the only thing that still believes in it.
    ONLY_IN_FILE = "only_in_file"
    #: Reported, and the file does not declare it. Somebody created a guest and
    #: did not write it down, so nothing knows whether it matters.
    ONLY_IN_PROVIDER = "only_in_provider"
    #: Reported with an address no declared network covers, so it has no zone.
    NO_ZONE = "no_zone"


@dataclass(frozen=True, slots=True)
class Divergence:
    """One disagreement, named with what it is about and what it means."""

    kind: DivergenceKind
    subject: str
    detail: str

    def to_record(self) -> dict[str, str]:
        """Return the JSON-serialisable form a report stores and a console marks a row with."""
        return {"kind": self.kind.value, "subject": self.subject, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class Annotation:
    """What a declared inventory says about one thing the provider reported.

    Keyed by the resource's correlation key — the value two descriptions of one
    thing agree on, which for a hypervisor guest is its cluster, kind and VMID.
    Not the native identifier: identity is derived from the provider's own name
    *plus a discriminator that keeps a reused VMID from inheriting a dead
    guest's history*, so it is deliberately not something a file can spell.

    A resource with no correlation key is therefore not annotatable, and is
    skipped rather than matched on something weaker. Matching an empty key
    against an empty one is the failure ``reconcile`` refuses for the same
    reason: the absence of a correlator is not a correlator.
    """

    correlation_key: str
    values: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EnrichmentPlan:
    """Everything one ingestion produced, before any of it is applied.

    Separated from the application so the ingestion can be tested against files
    and the application against an estate, and so a preview can show what a plan
    contains without touching the store.
    """

    zones: ZoneMap = ZoneMap()
    annotations: tuple[Annotation, ...] = ()
    #: The kinds the declared inventory speaks about. A resource of any other
    #: kind is neither annotated nor reported as undeclared: a file that
    #: describes nodes and guests says nothing about a disk, and reporting every
    #: disk as "not in the inventory" would bury the guest that genuinely is not.
    kinds: tuple[str, ...] = ()
    #: Problems the ingestion itself found — a declared entry with no identifier,
    #: a services file naming a workload nothing declares. Carried through so
    #: one report holds every disagreement rather than two halves of one.
    divergences: tuple[Divergence, ...] = ()

    def by_key(self) -> Mapping[str, Mapping[str, str]]:
        """Return the annotations keyed by the identifier they match on."""
        return {entry.correlation_key: entry.values for entry in self.annotations}


@dataclass(frozen=True, slots=True)
class EnrichmentReport:
    """What one application did, in the terms an operator would ask about."""

    source: str
    annotated: int = 0
    divergences: tuple[Divergence, ...] = ()
    dropped: tuple[str, ...] = ()
    screened: tuple[str, ...] = ()
    #: Whether the estate was larger than one page, so this pass annotated a
    #: prefix of it. Reported rather than silent: an enrichment that quietly
    #: covered the first five hundred resources of ten thousand would leave nine
    #: and a half thousand looking as though nobody had declared anything.
    truncated: bool = False

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-serialisable form stored beside the sweep and served."""
        return {
            "source": self.source,
            "annotated": self.annotated,
            "divergences": [entry.to_record() for entry in self.divergences],
            "dropped": list(self.dropped),
            "screened": list(self.screened),
            "truncated": self.truncated,
        }


async def apply_enrichment(
    gateway: PersistenceGateway,
    scope: TenantScope,
    *,
    plan: EnrichmentPlan,
    source: str,
    kinds: KindRegistry,
    at: datetime,
    limit: int = 0,
) -> EnrichmentReport:
    """Annotate what ``source`` reported, and report every disagreement.

    Runs after a sweep rather than inside one. Reconciliation replaces a
    resource's attributes with what the provider reported, so an annotation
    written during a sweep would survive exactly until the next one; running
    afterwards makes re-annotation part of every pass and therefore idempotent
    by construction rather than by care.

    ``limit`` of ``0`` means the estate's own page bound. Passing one is for the
    caller that already knows the estate is small.

    Nothing here creates a resource. A declared entry with nothing to annotate
    is a ``ONLY_IN_FILE`` divergence, which is the whole of "a resource present
    only in the file is a resource that no longer exists, and that is a finding".
    """
    declared = dict(plan.by_key())
    divergences: list[Divergence] = list(plan.divergences)
    dropped: set[str] = set()
    altered: set[str] = set()
    annotated = 0
    seen: set[str] = set()

    query = EstateQuery(
        sources=(source,),
        kinds=plan.kinds,
        include_absent=False,
        limit=limit or MAX_ESTATE_PAGE_SIZE,
    )

    async with gateway.begin(scope) as uow:
        # Paged rather than read once. An estate larger than one page used to
        # be enriched as far as its first page and reported as truncated, which
        # meant a resource beyond it silently kept the annotations it had —
        # 053 recorded that, 055 recorded it again, and this is where it stops.
        found = await whole_estate(uow.estate, query)
        for resource in found:
            key = resource.correlation_key
            if not key:
                continue
            seen.add(key)
            values = dict(declared.get(key, {}))
            address = str(resource.attributes.get(ADDRESS_ATTRIBUTE, ""))
            zone = plan.zones.zone_for(address)
            if zone:
                values["zone"] = zone
            elif _placeable(resource, kinds):
                divergences.append(_unplaced(resource, key, address))

            clean = typed(ANNOTATION_TYPES, values)
            dropped.update(clean.dropped)
            dropped.update(clean.invalid)
            checked = screened(clean.values)
            altered.update(checked.screened)

            annotated += int(bool(declared.get(key)))
            updated = _annotated(resource, checked.values, at=at)
            if updated != resource:
                await uow.estate.upsert(updated)

    divergences.extend(
        Divergence(
            kind=DivergenceKind.ONLY_IN_FILE,
            subject=native_id,
            detail=(
                f"declared in the inventory and not reported by {source}, so it no longer "
                f"exists as far as the live source is concerned"
            ),
        )
        for native_id in sorted(set(declared) - seen)
    )
    divergences.extend(
        Divergence(
            kind=DivergenceKind.ONLY_IN_PROVIDER,
            subject=native_id,
            detail=(
                f"reported by {source} and not declared in the inventory, so nothing says "
                f"what it is for or how much it matters"
            ),
        )
        for native_id in sorted(seen - set(declared))
        if declared
    )

    report = EnrichmentReport(
        source=source,
        annotated=annotated,
        truncated=len(found) >= query.limit,
        divergences=tuple(sorted(divergences, key=lambda entry: (entry.kind.value, entry.subject))),
        dropped=tuple(sorted(dropped)),
        screened=tuple(sorted(altered)),
    )
    logger.info(
        "estate.enrichment_applied",
        source=source,
        annotated=report.annotated,
        divergences=len(report.divergences),
        dropped=list(report.dropped),
    )
    return report


def _placeable(resource: Resource, kinds: KindRegistry) -> bool:
    """Return whether this resource is one a zone is expected of.

    A kind that declares an address is one whose resources sit on a network; a
    backup job does not, and reporting every one of them as unplaced would bury
    the guest that genuinely is.
    """
    declared = kinds.get(resource.kind).attributes if kinds.knows(resource.kind) else {}
    return ADDRESS_ATTRIBUTE in declared


def _unplaced(resource: Resource, key: str, address: str) -> Divergence:
    """Return the divergence for a resource no declared network covers."""
    return Divergence(
        kind=DivergenceKind.NO_ZONE,
        subject=key,
        detail=(
            f"{resource.display_name or resource.native_id} reports "
            f"{address or 'no address'}, which no declared network covers, so it carries "
            f"no zone"
        ),
    )


def _annotated(resource: Resource, values: Mapping[str, Any], *, at: datetime) -> Resource:
    """Return ``resource`` carrying ``values``, with the zone label kept in step.

    The label is rebuilt rather than added to: a guest that moved between
    networks would otherwise carry both zones, and a filter would find it under
    the one it left.
    """
    del at
    attributes = {
        name: value
        for name, value in resource.attributes.items()
        if name not in ANNOTATION_TYPES or name == ADDRESS_ATTRIBUTE
    }
    attributes.update(values)
    zone = str(values.get("zone", ""))
    labels = tuple(label for label in resource.labels if not label.startswith(ZONE_LABEL_PREFIX))
    if zone:
        labels = (*labels, f"{ZONE_LABEL_PREFIX}{zone}")
    return replace(resource, attributes=attributes, labels=labels)


def zone_networks(declared: Sequence[tuple[str, str]]) -> ZoneMap:
    """Return a zone map from ordered ``(cidr, name)`` pairs.

    A convenience for an ingestion that read an ordered document and wants the
    refusal to name the *first* overlap in file order rather than in whatever
    order a mapping happened to iterate.
    """
    return ZoneMap.of(dict(declared))


__all__ = [
    "ADDRESS_ATTRIBUTE",
    "ANNOTATION_TYPES",
    "ZONE_LABEL_PREFIX",
    "Annotation",
    "Divergence",
    "DivergenceKind",
    "EnrichmentPlan",
    "EnrichmentReport",
    "OverlappingZones",
    "ZoneMap",
    "apply_enrichment",
    "zone_networks",
]
