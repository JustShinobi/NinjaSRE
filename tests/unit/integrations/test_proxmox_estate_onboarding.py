"""The cluster as the first estate, at the size it actually is.

Every acceptance criterion this feature has, against a recorded two-node cluster
with fifty-seven containers and the operator's own inventory beside it. The
numbers are the fixture's declaration rather than this file's expectation, which
is what stops a test and a fixture from drifting into agreeing with each other
about the wrong figure.

What is proven here that no smaller test can:

- discovery finds two nodes and fifty-seven containers, and the per-zone counts
  are the ones the inventory declares;
- every resource that sits on a network carries a zone derived from its address,
  and nothing is silently left without one;
- criticality from the repository lands on each declared resource, and the two
  disagreements — one container gone, one undeclared — are reported as findings
  rather than dropped;
- stopping a container between two sweeps records a transition on the same
  resource instead of writing a second one;
- the graph holds a zone with its members and a domain resolving to the
  container that serves it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from integrations._base.retry import RetryPolicy
from integrations._base.transport import RequestContext
from integrations.proxmox.client import ProxmoxClient
from integrations.proxmox.discovery import PROXMOX_KINDS, ProxmoxDiscovery
from integrations.proxmox.enrichment import DirectoryInventory, ingest
from platform.estate.discovery.enriched import (
    DOMAIN_NODE_PREFIX,
    ZONE_NODE_PREFIX,
    EnrichingSweeper,
    enrichment_findings,
)
from platform.estate.discovery.sweep import EstateSweeper
from platform.estate.kinds import (
    KIND_CONTAINER,
    KIND_NODE,
    core_registry,
)
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import EstateQuery, TenantScope
from platform.persistence.ports.estate_repository import ResourceHealth
from tests.support.proxmox import CLUSTER
from tests.support.proxmox_estate import (
    GONE_VMID,
    GUESTS,
    RUNNING_GUESTS,
    STOPPED_VMIDS,
    TOTAL_GUESTS,
    UNDECLARED_VMID,
    ZONES,
    cluster_transport,
    write_inventory,
    zone_counts,
)

pytestmark = pytest.mark.unit

SCOPE = TenantScope(org_id="acme", team_node_id="homelab")
CONTEXT = RequestContext(org_id="acme", team_id="homelab", capability="proxmox_discovery")
FIRST = datetime(2026, 8, 10, 9, 0, tzinfo=UTC)
SECOND = FIRST + timedelta(minutes=5)


def _registry():  # type: ignore[no-untyped-def]
    """Return a registry holding the core kinds plus this integration's own."""
    registry = core_registry()
    for kind in PROXMOX_KINDS:
        registry.register(kind)
    return registry


def _source(*, stopped: frozenset[int] = STOPPED_VMIDS) -> ProxmoxDiscovery:
    """Return a discovery source over the recorded cluster."""
    transport = cluster_transport(stopped=stopped)
    return ProxmoxDiscovery(
        client=ProxmoxClient(
            transport=transport, context=CONTEXT, retry=RetryPolicy(max_attempts=1)
        )
    )


async def _store() -> FakePersistence:
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation(SCOPE.org_id, "Acme")
    return gateway


@pytest.fixture
def inventory(tmp_path: Path) -> DirectoryInventory:
    return DirectoryInventory(root=write_inventory(tmp_path))


async def _swept(
    inventory: DirectoryInventory,
    *,
    stopped: frozenset[int] = STOPPED_VMIDS,
    gateway: FakePersistence | None = None,
    at: datetime = FIRST,
):  # type: ignore[no-untyped-def]
    """Sweep the reference cluster and enrich it, returning the store and report."""
    store = gateway if gateway is not None else await _store()
    sweeper = EnrichingSweeper(sweeper=EstateSweeper(gateway=store, kinds=_registry()))
    plan = ingest(inventory, cluster=CLUSTER)
    outcome = await sweeper.sweep(SCOPE, _source(stopped=stopped), plan=plan, now=at)
    return store, outcome


# --- the fixture's own arithmetic ---------------------------------------------


def test_the_fixture_declares_the_cluster_the_acceptance_criteria_name() -> None:
    """The declaration this file's assertions are read against."""
    assert TOTAL_GUESTS == 57
    assert RUNNING_GUESTS == 49
    assert len(ZONES) == 7
    assert zone_counts() == {"infra": 25, "apps": 21, "dmz": 7, "ci": 2, "backup": 1, "vk8s": 1}


# --- acceptance 2: discovery finds the cluster --------------------------------


async def test_discovery_finds_two_nodes_and_fifty_seven_containers(
    inventory: DirectoryInventory,
) -> None:
    store, _ = await _swept(inventory)

    async with store.begin(SCOPE) as uow:
        nodes = await uow.estate.query(EstateQuery(kinds=(KIND_NODE,), limit=200))
        containers = await uow.estate.query(EstateQuery(kinds=(KIND_CONTAINER,), limit=200))

    assert len(nodes) == 2
    assert len(containers) == TOTAL_GUESTS


async def test_the_running_count_is_the_one_the_operator_would_recognise(
    inventory: DirectoryInventory,
) -> None:
    store, _ = await _swept(inventory)

    async with store.begin(SCOPE) as uow:
        containers = await uow.estate.query(EstateQuery(kinds=(KIND_CONTAINER,), limit=200))

    running = [resource for resource in containers if resource.health is ResourceHealth.HEALTHY]
    assert len(running) == RUNNING_GUESTS


# --- acceptance 3: every resource carries a zone -------------------------------


async def test_the_per_zone_counts_match_the_declared_inventory(
    inventory: DirectoryInventory,
) -> None:
    store, _ = await _swept(inventory)

    async with store.begin(SCOPE) as uow:
        containers = await uow.estate.query(EstateQuery(kinds=(KIND_CONTAINER,), limit=200))

    counted: dict[str, int] = {}
    for resource in containers:
        counted[str(resource.attributes["zone"])] = (
            counted.get(str(resource.attributes["zone"]), 0) + 1
        )
    assert counted == zone_counts()


async def test_no_resource_on_a_network_is_left_without_a_zone(
    inventory: DirectoryInventory,
) -> None:
    """Acceptance 3. Zero against this cluster, and impossible to lose against
    any other: an unplaced resource is a divergence entry rather than a blank."""
    store, outcome = await _swept(inventory)

    async with store.begin(SCOPE) as uow:
        placeable = await uow.estate.query(
            EstateQuery(kinds=(KIND_NODE, KIND_CONTAINER), limit=200)
        )

    assert placeable
    assert all(resource.attributes.get("zone") for resource in placeable)
    assert [
        entry for entry in outcome.enrichment.divergences if entry.kind.value == "no_zone"
    ] == []


async def test_a_zone_is_a_label_so_the_estate_can_be_filtered_by_it(
    inventory: DirectoryInventory,
) -> None:
    store, _ = await _swept(inventory)

    async with store.begin(SCOPE) as uow:
        in_dmz = await uow.estate.query(EstateQuery(labels=("zone:dmz",), limit=200))

    assert len(in_dmz) == zone_counts()["dmz"]


# --- acceptance 4: criticality, and the two disagreements ----------------------


async def test_criticality_from_the_repository_lands_on_every_declared_resource(
    inventory: DirectoryInventory,
) -> None:
    store, outcome = await _swept(inventory)

    async with store.begin(SCOPE) as uow:
        containers = await uow.estate.query(EstateQuery(kinds=(KIND_CONTAINER,), limit=200))

    declared = [
        resource for resource in containers if resource.native_id.split("/")[-1] != "unknown"
    ]
    with_criticality = [resource for resource in declared if resource.attributes.get("criticality")]
    assert len(with_criticality) == TOTAL_GUESTS - 1
    assert outcome.enrichment.annotated == TOTAL_GUESTS - 1 + 2


async def test_the_container_only_the_file_knows_about_is_a_finding(
    inventory: DirectoryInventory,
) -> None:
    """A resource present only in the file is one that no longer exists."""
    store, outcome = await _swept(inventory)

    only_in_file = [
        entry for entry in outcome.enrichment.divergences if entry.kind.value == "only_in_file"
    ]
    assert [entry.subject for entry in only_in_file] == [f"{CLUSTER}/lxc/{GONE_VMID}"]

    async with store.begin(SCOPE) as uow:
        containers = await uow.estate.query(EstateQuery(kinds=(KIND_CONTAINER,), limit=200))
    assert all(resource.correlation_key != f"{CLUSTER}/lxc/{GONE_VMID}" for resource in containers)


async def test_the_container_only_the_cluster_knows_about_is_a_finding_too(
    inventory: DirectoryInventory,
) -> None:
    store, outcome = await _swept(inventory)
    del store

    only_in_provider = [
        entry for entry in outcome.enrichment.divergences if entry.kind.value == "only_in_provider"
    ]
    assert [entry.subject for entry in only_in_provider] == [f"{CLUSTER}/lxc/{UNDECLARED_VMID}"]


async def test_the_divergence_report_is_kept_with_the_sweep_that_found_it(
    inventory: DirectoryInventory,
) -> None:
    """T-010. A finding in a log is a finding nobody can ask for in the morning."""
    store, outcome = await _swept(inventory)

    async with store.begin(SCOPE) as uow:
        record = await uow.estate.last_sweep("proxmox")

    assert record is not None
    findings = enrichment_findings(record.findings)
    assert findings["annotated"] == outcome.enrichment.annotated
    subjects = {entry["subject"] for entry in findings["divergences"]}
    assert subjects == {
        f"{CLUSTER}/lxc/{GONE_VMID}",
        f"{CLUSTER}/lxc/{UNDECLARED_VMID}",
    }


# --- acceptance 5: a stopped container is a transition ------------------------


async def test_stopping_a_container_records_a_transition_rather_than_a_rewrite(
    inventory: DirectoryInventory,
) -> None:
    """Acceptance 5. Same identity, same first-seen instant, one more transition."""
    victim = next(guest for guest in GUESTS if guest.running)
    store, _ = await _swept(inventory)

    async with store.begin(SCOPE) as uow:
        before = await uow.estate.by_correlation_key(
            kind=KIND_CONTAINER, correlation_key=victim.correlation_key
        )
    assert before is not None
    assert before.health is ResourceHealth.HEALTHY

    await _swept(
        inventory,
        stopped=frozenset({*STOPPED_VMIDS, victim.vmid}),
        gateway=store,
        at=SECOND,
    )

    async with store.begin(SCOPE) as uow:
        after = await uow.estate.by_correlation_key(
            kind=KIND_CONTAINER, correlation_key=victim.correlation_key
        )
        transitions = await uow.estate.transitions(before.resource_id, limit=10)
        containers = await uow.estate.query(EstateQuery(kinds=(KIND_CONTAINER,), limit=200))

    assert after is not None
    assert after.resource_id == before.resource_id
    assert after.first_seen_at == before.first_seen_at
    assert after.absent_since is None
    assert after.health is not ResourceHealth.HEALTHY
    assert len(containers) == TOTAL_GUESTS
    assert [entry.state for entry in transitions][:1] != []
    assert len({entry.state for entry in transitions}) == 2


async def test_sweeping_the_same_cluster_twice_changes_nothing_else(
    inventory: DirectoryInventory,
) -> None:
    """Enrichment runs after every sweep, so it has to be idempotent."""
    store, first = await _swept(inventory)
    _, second = await _swept(inventory, gateway=store, at=SECOND)

    assert first.enrichment.to_record() == second.enrichment.to_record()

    async with store.begin(SCOPE) as uow:
        containers = await uow.estate.query(EstateQuery(kinds=(KIND_CONTAINER,), limit=200))
    assert len(containers) == TOTAL_GUESTS
    assert all(sorted(resource.labels) == sorted(set(resource.labels)) for resource in containers)


# --- acceptance 6: the graph ---------------------------------------------------


async def test_a_nodes_topology_returns_its_guests(inventory: DirectoryInventory) -> None:
    """Acceptance 6, first half: a hypervisor's guests are reachable from it."""
    store, _ = await _swept(inventory)

    async with store.begin(SCOPE) as uow:
        nodes = await uow.estate.query(EstateQuery(kinds=(KIND_NODE,), limit=10))
        hosted = {
            reached.node_id
            for node in nodes
            for reached in (await uow.topology.direct_dependents(node.resource_id)).nodes
        }
        containers = await uow.estate.query(EstateQuery(kinds=(KIND_CONTAINER,), limit=200))

    assert {resource.resource_id for resource in containers} <= hosted


async def test_a_zone_holds_the_guests_that_depend_on_it(
    inventory: DirectoryInventory,
) -> None:
    store, outcome = await _swept(inventory)

    assert outcome.zones == len(zone_counts()) + 1  # the guests' zones, plus mgmt

    async with store.begin(SCOPE) as uow:
        members = (await uow.topology.direct_dependents(f"{ZONE_NODE_PREFIX}dmz")).nodes

    assert len(members) == zone_counts()["dmz"]


async def test_a_service_domain_resolves_to_the_container_that_serves_it(
    inventory: DirectoryInventory,
) -> None:
    """Acceptance 6, second half. The edge feature 055 resolves an alert through."""
    store, outcome = await _swept(inventory)
    served = next(guest for guest in GUESTS if guest.zone == "dmz")

    assert outcome.domains == 3

    async with store.begin(SCOPE) as uow:
        edges = await uow.topology.edges_from(f"{DOMAIN_NODE_PREFIX}{served.name}.example.internal")
        workload = await uow.estate.by_correlation_key(
            kind=KIND_CONTAINER, correlation_key=served.correlation_key
        )

    assert workload is not None
    assert [edge.to_node_id for edge in edges] == [workload.resource_id]
