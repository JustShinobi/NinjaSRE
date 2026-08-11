"""The starting document for a team's operating context, derived from the estate.

A person in front of an empty text box writes nothing. A person in front of five
headings, three of which already carry what this deployment has actually
discovered, fills in the other two — and the two left are exactly the ones no
sweep can answer: who is called, and what "critical" means to this team.

**Derived, never invented.** Everything in a derived section is something the
estate reports: the kinds it holds and how many of each, the zones its resources
carry and the network each zone's addresses sit in, the source that answers each
signal question. There is no model call here and there cannot be one — the
builder has no path to ``core.llm``, and a structural test holds that, because
"the deployment already knows this" and "a model wrote something plausible" are
different claims and an operator has no way to tell them apart afterwards.

**One fact ships whatever the estate looks like.** That a container's counters
are the host's, keyed by the guest's number, is a fact about how containers
report rather than a fact about this estate — and it is the one an investigation
gets confidently, plausibly wrong. It lands in the template before anybody has
swept anything.

**A zone's network is inferred, and says so.** Zone maps are declared at
ingestion and are not stored, so the network here is the prefix covering the
addresses the estate actually holds for that zone, at
``ALERT_ZONE_INFERENCE_PREFIX`` — the same rule and the same constant alert
resolution already uses to place an address no declared network covers. It is
offered as a starting line for somebody to correct, not as a statement of
record.

**Nothing here is written anywhere.** The template is a suggestion the read
route carries; it becomes configuration only when an operator saves it, and a
builder that stored its own output would be a deployment writing its own
operating context and attributing it to a person.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from ipaddress import ip_address, ip_network

from config.constants.estate import ALERT_ZONE_INFERENCE_PREFIX, MAX_ESTATE_PAGE_SIZE
from config.constants.signals import SIGNAL_QUESTIONS
from config.prompts.operating_context import (
    LXC_METRICS_FACT,
    TEMPLATE_DERIVED_LEAD,
    TEMPLATE_NOTHING_DISCOVERED,
    TEMPLATE_PROMPT_CRITICALITY,
    TEMPLATE_PROMPT_NETWORK,
    TEMPLATE_PROMPT_PEOPLE,
    TEMPLATE_PROMPT_WHAT_RUNS,
    TEMPLATE_SECTION_CRITICALITY,
    TEMPLATE_SECTION_NETWORK,
    TEMPLATE_SECTION_PEOPLE,
    TEMPLATE_SECTION_SIGNALS,
    TEMPLATE_SECTION_WHAT_RUNS,
)
from platform.estate.enrichment import ADDRESS_ATTRIBUTE
from platform.estate.signal_map import signal_map_for
from platform.persistence.ports.estate_repository import EstateQuery, Resource
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope

#: The attribute an operator's own inventory writes a resource's importance in.
CRITICALITY_ATTRIBUTE = "criticality"

#: The attribute a zone lands in once an enrichment has placed a resource.
ZONE_ATTRIBUTE = "zone"


@dataclass(frozen=True, slots=True)
class DiscoveredEstate:
    """What a sweep found, reduced to the four things the template says something about.

    A record rather than a bag of resources, so the rendering can be tested
    against a shape somebody wrote down and the derivation against an estate.
    """

    #: Kind to how many of it, in the order the template lists them: most first,
    #: because "forty-one containers and three nodes" is the sentence somebody
    #: would write and "three nodes and forty-one containers" is not.
    kinds: tuple[tuple[str, int], ...] = ()
    #: Zone name to the network its addresses sit in. Empty network where the
    #: estate holds no address for that zone.
    zones: tuple[tuple[str, str], ...] = ()
    #: Signal question to the integration answering it, in question order.
    signals: tuple[tuple[str, str], ...] = ()
    #: The criticality values an operator's own inventory actually uses.
    criticality: tuple[str, ...] = ()

    @property
    def empty(self) -> bool:
        """Return whether the estate has nothing to say yet."""
        return not (self.kinds or self.zones or self.signals or self.criticality)


def template_for(estate: DiscoveredEstate) -> tuple[tuple[str, str], ...]:
    """Return the starting sections for ``estate``, as ``(name, body)`` pairs.

    Five sections, always the same five and always in the same order, whether
    or not anything was discovered. A template whose shape depended on what a
    sweep found would give two deployments different questions to answer, and
    the questions are the half of this that is worth shipping.
    """
    return (
        (TEMPLATE_SECTION_WHAT_RUNS, _what_runs(estate)),
        (TEMPLATE_SECTION_NETWORK, _network(estate)),
        (TEMPLATE_SECTION_SIGNALS, _signals(estate)),
        (TEMPLATE_SECTION_CRITICALITY, _criticality(estate)),
        (TEMPLATE_SECTION_PEOPLE, TEMPLATE_PROMPT_PEOPLE),
    )


async def discovered_estate(
    gateway: PersistenceGateway,
    scope: TenantScope,
    *,
    configured_integrations: Sequence[str] = (),
    limit: int = 0,
) -> DiscoveredEstate:
    """Return what ``scope``'s estate reports, in the terms the template needs.

    One page. A template is a starting point somebody edits, and a count taken
    over the first five hundred resources of ten thousand is the right shape of
    sentence with the wrong number in it — which is why the counts are rendered
    as "at least", not as a total.
    """
    query = EstateQuery(include_absent=False, limit=limit or MAX_ESTATE_PAGE_SIZE)
    async with gateway.begin(scope) as uow:
        found = await uow.estate.query(query)
    return summarise(found, configured_integrations=configured_integrations)


def summarise(
    resources: Sequence[Resource], *, configured_integrations: Sequence[str] = ()
) -> DiscoveredEstate:
    """Return the four derivations ``resources`` support."""
    return DiscoveredEstate(
        kinds=_kind_counts(resources),
        zones=_zone_networks(resources),
        signals=_signal_sources(resources, configured_integrations),
        criticality=_criticality_values(resources),
    )


def _kind_counts(resources: Sequence[Resource]) -> tuple[tuple[str, int], ...]:
    """Return each kind and how many of it, most numerous first."""
    counted = Counter(resource.kind for resource in resources if resource.kind)
    return tuple(sorted(counted.items(), key=lambda entry: (-entry[1], entry[0])))


def _zone_networks(resources: Sequence[Resource]) -> tuple[tuple[str, str], ...]:
    """Return each zone and the network covering the addresses seen in it."""
    addresses: dict[str, list[str]] = {}
    for resource in resources:
        zone = str(resource.attributes.get(ZONE_ATTRIBUTE, "")).strip()
        if not zone:
            continue
        address = str(resource.attributes.get(ADDRESS_ATTRIBUTE, "")).strip()
        addresses.setdefault(zone, []).append(address)
    return tuple((zone, _covering(found)) for zone, found in sorted(addresses.items()))


def _covering(addresses: Sequence[str]) -> str:
    """Return the network the estate's own addresses put this zone on, or empty.

    Empty rather than a guess when the addresses disagree: a zone whose
    resources sit on two networks has no single answer, and offering one of them
    would put a line in front of an operator that is wrong in a way they would
    have to already know the answer to catch.
    """
    networks: set[str] = set()
    for address in addresses:
        candidate = address.split("/", 1)[0]
        if not candidate:
            continue
        try:
            ip_address(candidate)
        except ValueError:
            continue
        networks.add(str(ip_network(f"{candidate}/{ALERT_ZONE_INFERENCE_PREFIX}", strict=False)))
    return networks.pop() if len(networks) == 1 else ""


def _signal_sources(
    resources: Sequence[Resource], configured: Sequence[str]
) -> tuple[tuple[str, str], ...]:
    """Return the integration answering each signal question, in question order.

    Derived from the estate's own resources rather than from the list of
    installed integrations: which source answers "how much memory is this
    using" depends on what the resource *is*, and a container and a node do not
    have the same answer.
    """
    answering: dict[str, str] = {}
    for resource in resources:
        for source in signal_map_for(resource, configured=configured).sources:
            answering.setdefault(source.question, source.integration)
    return tuple(
        (question, answering[question]) for question in SIGNAL_QUESTIONS if question in answering
    )


def _criticality_values(resources: Sequence[Resource]) -> tuple[str, ...]:
    """Return the criticality vocabulary this deployment's own inventory uses."""
    found = {
        str(resource.attributes.get(CRITICALITY_ATTRIBUTE, "")).strip() for resource in resources
    }
    return tuple(sorted(value for value in found if value))


# --- rendering ----------------------------------------------------------------


def _what_runs(estate: DiscoveredEstate) -> str:
    """Return the body of the "what runs here" section."""
    if not estate.kinds:
        return _undiscovered(TEMPLATE_PROMPT_WHAT_RUNS)
    listed = "\n".join(f"- at least {count} × {kind}" for kind, count in estate.kinds)
    return f"{TEMPLATE_DERIVED_LEAD}\n{listed}\n\n{TEMPLATE_PROMPT_WHAT_RUNS}"


def _network(estate: DiscoveredEstate) -> str:
    """Return the body of the network section."""
    if not estate.zones:
        return _undiscovered(TEMPLATE_PROMPT_NETWORK)
    listed = "\n".join(
        f"- {zone} — {network}" if network else f"- {zone} — network not established"
        for zone, network in estate.zones
    )
    return f"{TEMPLATE_DERIVED_LEAD}\n{listed}\n\n{TEMPLATE_PROMPT_NETWORK}"


def _signals(estate: DiscoveredEstate) -> str:
    """Return the body of the signals section, which always carries the LXC fact."""
    if not estate.signals:
        return LXC_METRICS_FACT
    listed = "\n".join(f"- {question} — {source}" for question, source in estate.signals)
    return f"{LXC_METRICS_FACT}\n\n{TEMPLATE_DERIVED_LEAD}\n{listed}"


def _criticality(estate: DiscoveredEstate) -> str:
    """Return the body of the criticality section."""
    if not estate.criticality:
        return _undiscovered(TEMPLATE_PROMPT_CRITICALITY)
    listed = ", ".join(estate.criticality)
    return (
        f"{TEMPLATE_DERIVED_LEAD}\n- the inventory uses: {listed}\n\n{TEMPLATE_PROMPT_CRITICALITY}"
    )


def _undiscovered(prompt: str) -> str:
    """Return a section body that says why it is empty before it asks its question."""
    return f"{TEMPLATE_NOTHING_DISCOVERED}\n\n{prompt}"


def sections_of(template: Sequence[tuple[str, str]]) -> Mapping[str, str]:
    """Return ``template`` in the shape ``OperatingContext.sections`` takes."""
    return dict(template)


__all__ = [
    "CRITICALITY_ATTRIBUTE",
    "ZONE_ATTRIBUTE",
    "DiscoveredEstate",
    "discovered_estate",
    "sections_of",
    "summarise",
    "template_for",
]
