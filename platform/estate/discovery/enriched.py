"""A sweep, then what the deployment knows about what it found.

Three things happen after a pass over a provider, in this order, and the order
is the argument for the module existing at all.

**The sweep runs first and owns what exists.** Reconciliation replaces a
resource's attributes with what the provider reported, which means an annotation
written *during* a sweep survives exactly until the next one. Running afterwards
makes re-annotation part of every pass, so the estate converges on the same
answer however many times it is swept.

**Enrichment annotates, and cannot create.** The plan may only reach resources
the sweep stored. An entry the file declares and the provider does not report
becomes a divergence record, which is the whole of "a resource present only in
the file is a resource that no longer exists, and that is a finding".

**The graph is written last, from what was stored.** Zone nodes with the guests
that depend on them, and a service node per declared domain depending on the
workload that serves it. Both directions follow the graph's one rule — an edge
runs from the thing that would break to the thing whose failure would break it —
so a zone's gateway failing has every guest on that network in its blast radius,
and a domain that stops answering resolves to the container behind it.

The findings are then written onto the sweep's own row. A divergence report that
lived only in a log would be a finding nobody could ask for later, and "what did
last night's sweep disagree with the inventory about" is a question asked in the
morning.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from config.constants.estate import MAX_ESTATE_PAGE_SIZE
from platform.estate.discovery.port import DiscoveryMode, ResourceReader, SweepBudget
from platform.estate.discovery.sweep import EstateSweeper, SweepReport
from platform.estate.enrichment import (
    ZONE_LABEL_PREFIX,
    EnrichmentPlan,
    EnrichmentReport,
    apply_enrichment,
)
from platform.observability.logging import get_logger
from platform.persistence.ports.estate_repository import EstateQuery, Resource, whole_estate
from platform.persistence.ports.topology_graph import (
    EdgeKind,
    NodeKind,
    TopologyEdge,
    TopologyNode,
)
from platform.persistence.ports.transaction import TenantScope, UnitOfWork

logger = get_logger(__name__)

#: Where the enrichment's own report sits inside a sweep record's findings. One
#: key, named once, because the row is written here and read by a route.
FINDINGS_ENRICHMENT = "enrichment"

#: How a zone's graph node is identified. Prefixed so a zone called ``apps`` and
#: a service called ``apps`` are two nodes rather than one.
ZONE_NODE_PREFIX = "zone:"

#: How a declared domain's graph node is identified, for the same reason.
DOMAIN_NODE_PREFIX = "domain:"


@dataclass(frozen=True, slots=True)
class EnrichedSweep:
    """What one pass did, and what the deployment then knew about it."""

    sweep: SweepReport
    enrichment: EnrichmentReport
    #: Zone nodes written, and guest-to-zone edges. Reported rather than
    #: inferred from the graph, because a deployment without a graph store
    #: degrades to zero here and that is a fact worth being able to see.
    zones: int = 0
    domains: int = 0


@dataclass(slots=True)
class EnrichingSweeper:
    """Runs a sweep and then applies what the operator declared about it.

    Holds the sweeper rather than extending it. The sweep is the estate's own
    mechanism and is used unchanged by deployments with nothing declared; this
    is the composition that adds a second, slower source of truth on top.
    """

    sweeper: EstateSweeper

    async def sweep(
        self,
        scope: TenantScope,
        reader: ResourceReader,
        *,
        plan: EnrichmentPlan,
        now: datetime,
        mode: DiscoveryMode = DiscoveryMode.FULL,
        budget: SweepBudget | None = None,
        source: str = "",
    ) -> EnrichedSweep:
        """Sweep ``reader``, annotate what it stored, and write the graph.

        A sweep that failed is not enriched. Annotating an estate the provider
        could not be reached for would mark every resource in it as diverging
        from the inventory, which is a hundred findings about one outage.
        """
        report = await self.sweeper.sweep(
            scope, reader, now=now, mode=mode, budget=budget, source=source
        )
        if not report.concluded_absence:
            logger.info(
                "estate.enrichment_skipped",
                source=report.source,
                outcome=report.outcome.value,
                mode=report.mode.value,
            )
            return EnrichedSweep(sweep=report, enrichment=EnrichmentReport(source=report.source))

        enrichment = await apply_enrichment(
            self.sweeper.gateway,
            scope,
            plan=plan,
            source=report.source,
            kinds=self.sweeper.kinds,
            at=now,
        )

        async with self.sweeper.gateway.begin(scope) as uow:
            # The whole of this source's estate, paged. The graph this writes
            # is the estate's own shape, and a graph built from the first page
            # of a larger estate is a graph missing edges nobody can see are
            # missing.
            resources = await whole_estate(
                uow.estate, EstateQuery(sources=(report.source,), limit=MAX_ESTATE_PAGE_SIZE)
            )
            zones, domains = await _write_graph(uow, resources)
            stored = await uow.estate.last_sweep(report.source)
            if stored is not None and stored.sweep_id == report.sweep_id:
                await uow.estate.record_sweep(
                    replace(
                        stored,
                        findings={FINDINGS_ENRICHMENT: enrichment.to_record()},
                    )
                )

        return EnrichedSweep(sweep=report, enrichment=enrichment, zones=zones, domains=domains)


async def _write_graph(uow: UnitOfWork, resources: Sequence[Resource]) -> tuple[int, int]:
    """Return how many zones and domains were written into the topology graph.

    Never raises into a sweep. A deployment without a graph store degrades to a
    smaller answer; one that failed to record an estate because the graph was
    missing has no answer at all — which is the same line the sweep's own graph
    writing holds.
    """
    availability = await uow.topology.availability()
    if not availability.available:
        return 0, 0

    zones: dict[str, list[str]] = {}
    domains: dict[str, str] = {}
    for resource in resources:
        zone = str(resource.attributes.get("zone", ""))
        if zone:
            zones.setdefault(zone, []).append(resource.resource_id)
        domain = str(resource.attributes.get("domain", ""))
        if domain:
            domains[domain] = resource.resource_id

    for zone, members in sorted(zones.items()):
        node_id = f"{ZONE_NODE_PREFIX}{zone}"
        await uow.topology.upsert_node(
            TopologyNode(
                node_id=node_id,
                kind=NodeKind.ZONE,
                name=zone,
                properties={"members": len(members)},
            )
        )
        for member in members:
            # From the guest to the zone: a zone's gateway failing takes every
            # guest on that network with it, and the graph's one rule is that an
            # edge points at the thing whose failure would break the source.
            await uow.topology.upsert_edge(
                TopologyEdge(
                    from_node_id=member,
                    to_node_id=node_id,
                    kind=EdgeKind.DEPENDS_ON,
                    properties={"relation": ZONE_LABEL_PREFIX.rstrip(":")},
                )
            )

    for domain, workload in sorted(domains.items()):
        node_id = f"{DOMAIN_NODE_PREFIX}{domain}"
        await uow.topology.upsert_node(
            TopologyNode(
                node_id=node_id,
                kind=NodeKind.SERVICE,
                name=domain,
                properties={"domain": domain},
            )
        )
        await uow.topology.upsert_edge(
            TopologyEdge(
                from_node_id=node_id,
                to_node_id=workload,
                kind=EdgeKind.DEPENDS_ON,
                properties={"relation": "serves"},
            )
        )

    return len(zones), len(domains)


def enrichment_findings(findings: Mapping[str, object]) -> Mapping[str, object]:
    """Return the enrichment half of a sweep's findings, or an empty mapping.

    A reader rather than an attribute access, so a sweep recorded before this
    post-step existed reads as "nothing was concluded" instead of raising in a
    route.
    """
    found = findings.get(FINDINGS_ENRICHMENT)
    return found if isinstance(found, dict) else {}


__all__ = [
    "DOMAIN_NODE_PREFIX",
    "FINDINGS_ENRICHMENT",
    "ZONE_NODE_PREFIX",
    "EnrichedSweep",
    "EnrichingSweeper",
    "enrichment_findings",
]
