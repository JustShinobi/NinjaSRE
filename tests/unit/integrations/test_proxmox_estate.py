"""The definition of done's second line: discovery populates the estate.

Everything else about this integration is provable one layer at a time. This is
the one that only means anything end to end — the sweep, the kind registry, the
identity derivation, the health mapping and the repository, with a recorded
two-node cluster on the far side and nothing mocked in between.

What it proves that a page of ``DiscoveredResource`` cannot:

- the kinds this integration declares are ones the registry accepts, so nothing
  is silently dropped mid-sweep for being undeclared;
- the attributes survive the estate's own typing, which discards anything the
  kind did not declare — a resource that arrived with the wrong attribute names
  would store as an empty one and look fine in the page;
- parentage resolves, so a guest hangs off a node and a node off the cluster in
  the *repository* rather than only in the payload;
- a second sweep of an unchanged cluster updates rather than duplicating, which
  is what identity is for and what a single-sweep test cannot see.

The two structural tests at the end are T-039 and SC-010: every capability this
integration declares reads, and every public read on the client is exercised by
the suite against recorded responses rather than a live cluster.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from core.capability.metadata import SideEffectLevel
from core.capability.registered import capability_marker
from integrations._base.retry import RetryPolicy
from integrations._base.transport import RequestContext
from integrations.proxmox import tools as proxmox_tools
from integrations.proxmox.client import ProxmoxClient
from integrations.proxmox.discovery import PROXMOX_KINDS, ProxmoxDiscovery
from integrations.proxmox.schema import API_BASE
from integrations.proxmox_backup_server import tools as backup_tools
from platform.credentials.proxy.model import OutboundResponse, ProxyRequest
from platform.estate.discovery.sweep import EstateSweeper
from platform.estate.kinds import (
    KIND_CLUSTER,
    KIND_CONTAINER,
    KIND_NODE,
    core_registry,
)
from platform.persistence.fakes import FakePersistence
from platform.persistence.ports import EstateQuery, TenantScope
from platform.persistence.ports.estate_repository import ResourceHealth
from tests.support.proxmox import PRIMARY, SECONDARY, ClusterState, recorded

pytestmark = pytest.mark.unit

SCOPE = TenantScope(org_id="acme", team_node_id="homelab")
CONTEXT = RequestContext(org_id="acme", team_id="homelab", capability="proxmox_discovery")
NO_RETRY = RetryPolicy(max_attempts=1)
AT = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)

TESTS_ROOT = Path(__file__).resolve().parent


@dataclass(slots=True)
class RecordedTransport:
    """The recorded cluster, behind the proxy transport protocol."""

    state: ClusterState = ClusterState.HEALTHY
    calls: list[str] = field(default_factory=list)

    async def forward(self, request: ProxyRequest) -> OutboundResponse:
        """Answer ``request`` from the recording."""
        path = urlsplit(request.url).path.removeprefix(API_BASE)
        self.calls.append(path)
        try:
            payload = recorded(self.state).payload(path)
        except KeyError:
            return OutboundResponse(595, {}, b"595 no route to host")
        return OutboundResponse(
            200,
            {"content-type": "application/json"},
            json.dumps({"data": payload}).encode("utf-8"),
        )


def registry_with_proxmox_kinds():
    """Return a kind registry holding the core kinds and the three Proxmox adds."""
    registry = core_registry()
    for kind in PROXMOX_KINDS:
        registry.register(kind)
    registry.seal()
    return registry


def source(state: ClusterState = ClusterState.HEALTHY) -> ProxmoxDiscovery:
    """Return a discovery source over the recorded cluster in ``state``."""
    client = ProxmoxClient(
        transport=RecordedTransport(state=state), context=CONTEXT, retry=NO_RETRY
    )
    return ProxmoxDiscovery(client=client)


async def test_a_sweep_of_the_reference_cluster_lands_in_the_estate() -> None:
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme")
    sweeper = EstateSweeper(gateway=gateway, kinds=registry_with_proxmox_kinds())

    report = await sweeper.sweep(SCOPE, source(), now=AT)

    async with gateway.begin(SCOPE) as uow:
        stored = await uow.estate.query(EstateQuery())

    assert report.discovered == len(stored)
    kinds = {resource.kind for resource in stored}
    assert {KIND_CLUSTER, KIND_NODE, KIND_CONTAINER} <= kinds


async def test_the_stored_cluster_keeps_the_attributes_its_kind_declares() -> None:
    """A resource whose attributes the kind never declared stores as an empty one."""
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme")
    sweeper = EstateSweeper(gateway=gateway, kinds=registry_with_proxmox_kinds())

    await sweeper.sweep(SCOPE, source(), now=AT)

    async with gateway.begin(SCOPE) as uow:
        stored = await uow.estate.query(EstateQuery(kinds=(KIND_CLUSTER,)))

    assert len(stored) == 1
    assert stored[0].attributes["node_count"] == 2
    assert stored[0].attributes["quorate"] is True


async def test_guests_hang_off_their_node_and_nodes_off_the_cluster_in_the_repository() -> None:
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme")
    sweeper = EstateSweeper(gateway=gateway, kinds=registry_with_proxmox_kinds())

    await sweeper.sweep(SCOPE, source(), now=AT)

    async with gateway.begin(SCOPE) as uow:
        stored = {
            resource.resource_id: resource for resource in await uow.estate.query(EstateQuery())
        }

    cluster = next(found for found in stored.values() if found.kind == KIND_CLUSTER)
    nodes = [found for found in stored.values() if found.kind == KIND_NODE]
    containers = [found for found in stored.values() if found.kind == KIND_CONTAINER]

    assert nodes and all(found.parent_id == cluster.resource_id for found in nodes)
    node_ids = {found.resource_id for found in nodes}
    assert containers and all(found.parent_id in node_ids for found in containers)


async def test_a_second_sweep_of_an_unchanged_cluster_updates_rather_than_duplicating() -> None:
    """SC-005's other half, at the estate rather than at the identity function."""
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme")
    sweeper = EstateSweeper(gateway=gateway, kinds=registry_with_proxmox_kinds())

    first = await sweeper.sweep(SCOPE, source(), now=AT)
    await sweeper.sweep(SCOPE, source(), now=AT)

    async with gateway.begin(SCOPE) as uow:
        stored = await uow.estate.query(EstateQuery())

    assert len(stored) == first.discovered


async def test_a_down_nodes_guests_are_stored_as_unknown_rather_than_removed() -> None:
    """SC-006, at the estate: stale, not absent."""
    gateway = FakePersistence()
    async with gateway.begin_system() as system:
        await system.orgs.create_organisation("acme", "Acme")
    sweeper = EstateSweeper(gateway=gateway, kinds=registry_with_proxmox_kinds())

    await sweeper.sweep(SCOPE, source(), now=AT)
    await sweeper.sweep(SCOPE, source(ClusterState.NODE_DOWN), now=AT)

    async with gateway.begin(SCOPE) as uow:
        stored = await uow.estate.query(EstateQuery(kinds=(KIND_CONTAINER,)))

    on_down_node = [found for found in stored if found.attributes.get("cores")]
    assert on_down_node, "the down node's guests were removed from the estate"
    assert any(found.health is ResourceHealth.UNKNOWN for found in stored)
    gone = [found for found in stored if found.health is ResourceHealth.ABSENT]
    assert not gone, "a node that stopped answering is not a guest that was deleted"


# --- T-039 and SC-010, structurally ------------------------------------------


def test_every_capability_this_integration_declares_reads() -> None:
    """T-039. A write in this package would be one typo from being called as a read."""
    declared = []
    for package in (proxmox_tools, backup_tools):
        for attribute in vars(package).values():
            registered = capability_marker(attribute)
            if registered is not None:
                declared.append(registered)

    assert declared, "the walk found no capabilities, so this asserts nothing"
    for registered in declared:
        assert registered.metadata.side_effect_level is SideEffectLevel.READ, (
            f"{registered.name} declares {registered.metadata.side_effect_level}"
        )
        assert not registered.metadata.requires_approval


def test_every_public_read_on_the_client_is_exercised_against_recorded_responses() -> None:
    """SC-010. "The whole client" is a claim, and this is what makes it one."""
    methods = {
        name
        for name, member in vars(ProxmoxClient).items()
        if not name.startswith("_") and inspect.iscoroutinefunction(member)
    }
    exercised = "".join(
        path.read_text(encoding="utf-8") for path in sorted(TESTS_ROOT.glob("test_proxmox_*.py"))
    )

    unexercised = sorted(name for name in methods if f".{name}(" not in exercised)

    assert not unexercised, (
        f"these client reads are never exercised against the recorded cluster: {unexercised}"
    )


def test_no_proxmox_test_reaches_a_live_cluster() -> None:
    """NFR-004, and the reason the corpus exists at all."""
    banned = ("192.168.", "https://pve", "socket.", "httpx", "requests.get")
    offenders = [
        f"{path.name}: {word}"
        for path in sorted(TESTS_ROOT.glob("test_proxmox_*.py"))
        # This file names the words in order to ban them, which would otherwise
        # make it the only offender the check ever finds.
        if path.name != Path(__file__).name
        for word in banned
        if word in path.read_text(encoding="utf-8")
    ]

    assert not offenders, "\n".join(offenders)


def test_the_recorded_corpus_covers_every_state_the_feature_names() -> None:
    """T-040: healthy, degraded, no-quorum, node-down and single-node-no-cluster."""
    assert {state.value for state in ClusterState} == {
        "healthy",
        "degraded",
        "no_quorum",
        "node_down",
        "single_node",
    }
    for state in ClusterState:
        corpus = recorded(state)
        assert "/cluster/status" in corpus.paths()
        assert corpus.payload("/cluster/status")


def test_the_corpus_describes_the_two_nodes_the_wave_targets() -> None:
    assert {PRIMARY, SECONDARY} == {"pve01", "pve02"}
