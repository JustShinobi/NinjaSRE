"""The four cases where "is this the same thing" has a non-obvious answer.

Two integrations describing one machine. A guest that moved between nodes. A
provider that reused an identifier after a deletion. A source that cannot name
what it is reporting. Each of them is a way an estate silently becomes wrong.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from platform.estate.discovery.port import (
    DiscoveredResource,
    DiscoveryDeclaration,
    DiscoveryMode,
    DiscoveryPage,
    SweepBudget,
)
from platform.estate.discovery.reconcile import GENERATION_SEPARATOR
from platform.estate.discovery.sweep import EstateSweeper
from platform.estate.identity import derive_resource_id
from platform.estate.kinds import KIND_NODE, KIND_VIRTUAL_MACHINE, core_registry
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import (
    EstateQuery,
    PersistenceGateway,
    ResourceHealth,
    TenantScope,
)
from platform.persistence.ports.topology_graph import EdgeKind

pytestmark = pytest.mark.unit

ORG = "acme"
EPOCH = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def at(minutes: float = 0.0) -> datetime:
    """Return a fixed instant offset by ``minutes``."""
    return EPOCH + timedelta(minutes=minutes)


@dataclass
class FakeReader:
    """A source that answers everything in one page."""

    integration: str
    resources: tuple[DiscoveredResource, ...] = ()
    kinds: tuple[str, ...] = (KIND_NODE, KIND_VIRTUAL_MACHINE)
    calls: list[str] = field(default_factory=list)

    @property
    def declaration(self) -> DiscoveryDeclaration:
        """Return what this source says about itself."""
        return DiscoveryDeclaration(integration=self.integration, kinds=self.kinds)

    async def discover(
        self,
        *,
        mode: DiscoveryMode,
        cursor: str = "",
        budget: SweepBudget,
    ) -> DiscoveryPage:
        """Return everything in one page."""
        self.calls.append(cursor)
        return DiscoveryPage(resources=self.resources, complete=True)


@pytest.fixture
async def gateway() -> PersistenceGateway:
    """Return a store with one organisation."""
    store = FakePersistence()
    async with store.begin_system() as system:
        await system.orgs.create_organisation(ORG, "Acme")
    return store


@pytest.fixture
def scope() -> TenantScope:
    """Return the tenant every sweep here runs for."""
    return TenantScope(org_id=ORG)


@pytest.fixture
def sweeper(gateway: PersistenceGateway) -> EstateSweeper:
    """Return a sweeper over the core kinds."""
    return EstateSweeper(gateway=gateway, kinds=core_registry())


# --- Two sources, one thing (SC-004) -------------------------------------------


async def test_two_sources_describing_one_machine_reconcile_to_one_resource(
    sweeper: EstateSweeper, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    hypervisor = FakeReader(
        integration="proxmox",
        resources=(
            DiscoveredResource(
                kind=KIND_NODE,
                native_id="node/pve1",
                display_name="pve1",
                correlation_key="uuid:4c4c4544-0037",
                attributes={"cpu_count": 16},
                provider_status="online",
            ),
        ),
    )
    monitoring = FakeReader(
        integration="prometheus",
        resources=(
            DiscoveredResource(
                kind=KIND_NODE,
                native_id="instance/10.0.0.11:9100",
                display_name="pve1.lan",
                correlation_key="uuid:4c4c4544-0037",
                attributes={"load_average": 3.5},
                provider_status="up",
            ),
        ),
    )

    await sweeper.sweep(scope, hypervisor, now=at())
    await sweeper.sweep(scope, monitoring, now=at(1))

    async with gateway.begin(scope) as uow:
        stored = await uow.estate.query(EstateQuery())

    assert len(stored) == 1
    both = stored[0]
    assert {entry.integration for entry in both.sources} == {"proxmox", "prometheus"}
    # Each source's own view of the machine is attributable to it.
    by_source = {entry.integration: entry for entry in both.sources}
    assert by_source["proxmox"].native_id == "node/pve1"
    assert by_source["prometheus"].native_id == "instance/10.0.0.11:9100"
    assert by_source["prometheus"].attributes == {"load_average": 3.5}
    # The first source to describe it stays the primary one, so a second
    # integration arriving does not reassign the estate.
    assert both.source == "proxmox"


async def test_an_empty_correlation_key_never_matches_another_empty_one(
    sweeper: EstateSweeper, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    reader = FakeReader(
        integration="proxmox",
        resources=(
            DiscoveredResource(kind=KIND_NODE, native_id="node/a", display_name="a"),
            DiscoveredResource(kind=KIND_NODE, native_id="node/b", display_name="b"),
        ),
    )

    await sweeper.sweep(scope, reader, now=at())

    async with gateway.begin(scope) as uow:
        assert len(await uow.estate.query(EstateQuery())) == 2


async def test_a_second_source_sweeping_twice_does_not_stack_contributions(
    sweeper: EstateSweeper, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    hypervisor = FakeReader(
        integration="proxmox",
        resources=(
            DiscoveredResource(
                kind=KIND_NODE,
                native_id="node/pve1",
                correlation_key="uuid:1",
                provider_status="online",
            ),
        ),
    )
    monitoring = FakeReader(
        integration="prometheus",
        resources=(
            DiscoveredResource(
                kind=KIND_NODE,
                native_id="instance/1",
                correlation_key="uuid:1",
                provider_status="up",
            ),
        ),
    )
    await sweeper.sweep(scope, hypervisor, now=at())
    await sweeper.sweep(scope, monitoring, now=at(1))
    await sweeper.sweep(scope, monitoring, now=at(2))

    async with gateway.begin(scope) as uow:
        stored = await uow.estate.query(EstateQuery())

    assert len(stored) == 1
    assert len(stored[0].sources) == 2


# --- A guest that moved --------------------------------------------------------


async def test_a_guest_migrated_between_nodes_moves_rather_than_duplicating(
    sweeper: EstateSweeper, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    def cluster(node_of_guest: str) -> FakeReader:
        return FakeReader(
            integration="proxmox",
            resources=(
                DiscoveredResource(kind=KIND_NODE, native_id="node/pve1", display_name="pve1"),
                DiscoveredResource(kind=KIND_NODE, native_id="node/pve2", display_name="pve2"),
                DiscoveredResource(
                    kind=KIND_VIRTUAL_MACHINE,
                    native_id="qemu/101",
                    display_name="checkout",
                    parent_native_id=node_of_guest,
                    provider_status="running",
                ),
            ),
        )

    await sweeper.sweep(scope, cluster("node/pve1"), now=at())
    await sweeper.sweep(scope, cluster("node/pve2"), now=at(15))

    guest_id = derive_resource_id(source="proxmox", native_id="qemu/101")
    pve2 = derive_resource_id(source="proxmox", native_id="node/pve2")

    async with gateway.begin(scope) as uow:
        stored = await uow.estate.query(EstateQuery())
        guest = await uow.estate.get(guest_id)
        edges = await uow.topology.edges_from(guest_id)

    assert len(stored) == 3
    assert guest is not None
    assert guest.parent_id == pve2
    # The old edge is removed rather than left. Every traversal returns nodes,
    # so a retired edge would be indistinguishable from a live one.
    hosted = [edge for edge in edges if edge.kind is EdgeKind.HOSTED_ON]
    assert [edge.to_node_id for edge in hosted] == [pve2]


# --- A reused identifier -------------------------------------------------------


async def test_a_reused_provider_identifier_produces_a_new_resource(
    sweeper: EstateSweeper, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """The old resource keeps its history; the newcomer does not inherit it."""
    original = FakeReader(
        integration="proxmox",
        resources=(
            DiscoveredResource(
                kind=KIND_VIRTUAL_MACHINE,
                native_id="qemu/101",
                display_name="old-billing",
                provider_status="stopped",
            ),
        ),
    )
    await sweeper.sweep(scope, original, now=at())

    # Deleted: a complete sweep reports it gone.
    await sweeper.sweep(scope, FakeReader(integration="proxmox"), now=at(15))

    # And later the provider hands 101 to something else entirely.
    successor = FakeReader(
        integration="proxmox",
        resources=(
            DiscoveredResource(
                kind=KIND_VIRTUAL_MACHINE,
                native_id="qemu/101",
                display_name="new-checkout",
                provider_status="running",
            ),
        ),
    )
    await sweeper.sweep(scope, successor, now=at(30))

    retired_id = derive_resource_id(source="proxmox", native_id="qemu/101")
    async with gateway.begin(scope) as uow:
        everything = await uow.estate.query(EstateQuery(include_absent=True))
        retired = await uow.estate.get(retired_id)
        live = await uow.estate.by_native_id(source="proxmox", native_id="qemu/101")
        successor_history = await uow.estate.transitions(live.resource_id) if live else ()

    assert len(everything) == 2
    assert retired is not None
    assert retired.display_name == "old-billing"
    assert retired.absent_since == at(15)
    assert live is not None
    assert live.resource_id != retired_id
    assert live.resource_id.startswith(f"{retired_id}{GENERATION_SEPARATOR}")
    assert live.display_name == "new-checkout"
    # The newcomer's history is its own, and starts where it started.
    assert [entry.state for entry in successor_history] == [ResourceHealth.HEALTHY]


async def test_a_resource_that_comes_back_before_being_marked_absent_is_the_same_one(
    sweeper: EstateSweeper, gateway: PersistenceGateway, scope: TenantScope
) -> None:
    """A guest that was merely restarted is not a new guest."""
    reader = FakeReader(
        integration="proxmox",
        resources=(
            DiscoveredResource(
                kind=KIND_VIRTUAL_MACHINE,
                native_id="qemu/101",
                display_name="checkout",
                provider_status="stopped",
            ),
        ),
    )
    await sweeper.sweep(scope, reader, now=at())
    reader.resources = (
        DiscoveredResource(
            kind=KIND_VIRTUAL_MACHINE,
            native_id="qemu/101",
            display_name="checkout",
            provider_status="running",
        ),
    )
    await sweeper.sweep(scope, reader, now=at(15))

    async with gateway.begin(scope) as uow:
        stored = await uow.estate.query(EstateQuery())
        history = await uow.estate.transitions(stored[0].resource_id)

    assert len(stored) == 1
    assert [entry.state for entry in history] == [
        ResourceHealth.HEALTHY,
        ResourceHealth.UNHEALTHY,
    ]
