"""The three ways topology gets into the graph, and what each of them refuses.

An import file is the source of truth for the part of the estate no adapter can
see, so it is strict: every problem is reported at once, and an edge naming a
service the file does not declare is a typo rather than a discovery.

A discovery adapter is the opposite: it reports what it saw and how much of the
estate that was, and it never raises. A cluster that cannot be reached is a
health signal, not an exception — because the caller's next decision depends on
telling "gone" from "not seen", and an exception carries neither.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from config.constants.knowledge import MESH_EDGE_MIN_REQUESTS, TRACE_EDGE_MIN_SPANS
from platform.knowledge.errors import ImportInvalid, UnknownDependency
from platform.knowledge.topology.discovery.kubernetes import KubernetesDiscovery
from platform.knowledge.topology.discovery.mesh import ObservedTraffic, ServiceMeshDiscovery
from platform.knowledge.topology.discovery.port import DiscoveryHealth
from platform.knowledge.topology.discovery.traces import ObservedSpanEdge, TraceDiscovery
from platform.knowledge.topology.import_ import TopologyImporter, parse_topology
from platform.knowledge.topology.models import DependencyKind
from platform.knowledge.topology.queries import TopologyQueries
from platform.knowledge.topology.write import TopologyWriter
from platform.persistence.ports import NodeKind, PersistenceGateway, TenantScope
from tests.unit.platform.knowledge.conftest import Clock

pytestmark = pytest.mark.unit

DOCUMENT = """
version: 1
services:
  - id: checkout
    kind: service
    environment: prod
    owner: team-payments
    annotations:
      note: fronted by the CDN
  - id: payments
    kind: service
  - id: payments-db
    kind: database
dependencies:
  - from: checkout
    to: payments
    kind: calls
  - from: payments
    to: payments-db
    kind: reads_from
    annotations:
      note: read replica only
"""


class FakeCluster:
    """A cluster reader over fixed objects, with per-read failures."""

    def __init__(
        self,
        *,
        services: Sequence[Mapping[str, Any]] = (),
        workloads: Sequence[Mapping[str, Any]] = (),
        endpoints: Sequence[Mapping[str, Any]] = (),
        failing: frozenset[str] = frozenset(),
    ) -> None:
        self._services = services
        self._workloads = workloads
        self._endpoints = endpoints
        self._failing = failing

    async def services(self) -> Sequence[Mapping[str, Any]]:
        """Return the Service objects, or fail if this read is configured to."""
        return self._answer("services", self._services)

    async def workloads(self) -> Sequence[Mapping[str, Any]]:
        """Return the workload objects, or fail if this read is configured to."""
        return self._answer("workloads", self._workloads)

    async def endpoints(self) -> Sequence[Mapping[str, Any]]:
        """Return the Endpoints objects, or fail if this read is configured to."""
        return self._answer("endpoints", self._endpoints)

    def _answer(
        self, what: str, objects: Sequence[Mapping[str, Any]]
    ) -> Sequence[Mapping[str, Any]]:
        if what in self._failing:
            raise TimeoutError(f"the {what} read timed out")
        return objects


class FakeMesh:
    """A mesh reader over fixed observations."""

    def __init__(self, *observations: ObservedTraffic, failing: bool = False) -> None:
        self._observations = observations
        self._failing = failing

    async def traffic(self) -> Sequence[ObservedTraffic]:
        """Return the observed traffic, or fail if configured to."""
        if self._failing:
            raise ConnectionError("the mesh telemetry endpoint refused the connection")
        return self._observations


class FakeTraces:
    """A trace reader over fixed span edges."""

    def __init__(self, *edges: ObservedSpanEdge) -> None:
        self._edges = edges

    async def span_edges(self) -> Sequence[ObservedSpanEdge]:
        """Return the observed span edges."""
        return self._edges


# --- Declarative import -------------------------------------------------------


async def test_a_declarative_document_populates_the_graph(
    gateway: PersistenceGateway, scope: TenantScope, clock: Clock
) -> None:
    """FR-006: topology as code, applied and re-appliable."""
    importer = TopologyImporter(gateway=gateway, scope=scope, clock=clock)

    report = await importer.apply_text(DOCUMENT)

    assert report.services == 3
    assert report.dependencies == 2

    queries = TopologyQueries(gateway=gateway, scope=scope, clock=clock)
    answer = await queries.query("checkout", depth=2)

    assert sorted(answer.dependencies.names()) == ["payments", "payments-db"]
    edges = {edge.key: edge for edge in await queries.dependency_edges("payments")}
    assert edges[("payments", "payments-db", "reads_from")].annotations["note"] == (
        "read replica only"
    )


async def test_an_imported_record_is_operator_authored(
    gateway: PersistenceGateway, scope: TenantScope, clock: Clock
) -> None:
    # Which is what stops the next discovery run removing the dependency the
    # file exists to record.
    importer = TopologyImporter(gateway=gateway, scope=scope, clock=clock)
    await importer.apply_text(DOCUMENT)

    queries = TopologyQueries(gateway=gateway, scope=scope, clock=clock)
    edges = await queries.dependency_edges("checkout")

    assert all(edge.operator_authored for edge in edges)
    services = (await queries.query("checkout")).dependencies.services
    assert all(service.operator_authored for service in services)


def test_the_parser_reports_every_problem_at_once() -> None:
    """An operator fixing a file one error per run stops using the file."""
    with pytest.raises(ImportInvalid) as failure:
        parse_topology(
            """
            version: 2
            services:
              - kind: service
              - id: checkout
                kind: teapot
              - id: payments
            dependencies:
              - from: checkout
                to: paymnets
            """
        )

    problems = "\n".join(failure.value.problems)
    assert "version 2" in problems
    assert "services[0] has no 'id'" in problems
    assert "kind 'teapot'" in problems
    assert "'paymnets'" in problems


def test_a_document_that_is_not_a_mapping_is_refused() -> None:
    with pytest.raises(ImportInvalid):
        parse_topology("- just\n- a list\n")


def test_a_service_kind_survives_the_round_trip() -> None:
    document = parse_topology(DOCUMENT)
    kinds = {service.node_id: service.kind for service in document.services}

    assert kinds["payments-db"] is NodeKind.DATABASE


# --- Manual entry -------------------------------------------------------------


async def test_annotating_a_dependency_that_does_not_exist_is_refused(
    gateway: PersistenceGateway, scope: TenantScope, clock: Clock
) -> None:
    # Creating it on the operator's behalf would turn a typo into topology that
    # discovery then declines to remove, because it would be operator-authored.
    writer = TopologyWriter(gateway=gateway, scope=scope, clock=clock)

    with pytest.raises(UnknownDependency):
        await writer.annotate_dependency(
            "checkout", "paymnets", DependencyKind.CALLS, {"note": "typo"}
        )


async def test_annotating_a_service_the_graph_has_never_seen_creates_it(
    gateway: PersistenceGateway, scope: TenantScope, clock: Clock
) -> None:
    # Recording what you know about a system before any adapter reaches it is
    # the case hand-entry exists for.
    writer = TopologyWriter(gateway=gateway, scope=scope, clock=clock)

    service = await writer.annotate_service("mainframe", {"note": "batch window is 02:00-04:00"})

    assert service.annotations["note"].startswith("batch window")
    assert service.operator_authored is True


# --- Kubernetes ---------------------------------------------------------------


async def test_kubernetes_discovery_reads_services_owners_and_declared_dependencies() -> None:
    cluster = FakeCluster(
        services=[
            {
                "metadata": {
                    "name": "checkout",
                    "namespace": "prod",
                    "labels": {"app.kubernetes.io/part-of": "team-payments"},
                    "annotations": {"ninjasre.io/depends-on": "prod/payments, external/stripe"},
                }
            }
        ],
        endpoints=[
            {
                "metadata": {"name": "checkout", "namespace": "prod"},
                "subsets": [
                    {
                        "addresses": [
                            {
                                "targetRef": {
                                    "kind": "Pod",
                                    "name": "checkout-7f9dd-x7gr9",
                                    "namespace": "prod",
                                }
                            }
                        ]
                    }
                ],
            }
        ],
    )

    found = await KubernetesDiscovery(reader=cluster).discover()

    assert found.health is DiscoveryHealth.HEALTHY
    services = {node.node_id: node for node in found.nodes}
    assert services["prod/checkout"].owner == "team-payments"
    assert services["prod/checkout"].environment == "prod"
    assert ("prod/checkout", "prod/payments", "depends_on") in found.edges_by_key()
    assert ("prod/checkout", "external/stripe", "depends_on") in found.edges_by_key()


async def test_kubernetes_discovery_follows_owner_references_to_the_workload() -> None:
    # A pod's immediate owner is a ReplicaSet, which is gone after the next
    # rollout — following it would put a hash-suffixed node in the graph.
    cluster = FakeCluster(
        endpoints=[
            {
                "metadata": {"name": "checkout", "namespace": "prod"},
                "subsets": [
                    {
                        "addresses": [
                            {
                                "targetRef": {
                                    "kind": "Pod",
                                    "name": "checkout-7f9dd-x7gr9",
                                    "namespace": "prod",
                                    "ownerReferences": [
                                        {"kind": "ReplicaSet", "name": "checkout-7f9dd"},
                                        {"kind": "Deployment", "name": "checkout"},
                                    ],
                                }
                            }
                        ]
                    }
                ],
            }
        ]
    )

    found = await KubernetesDiscovery(reader=cluster).discover()

    assert ("prod/checkout", "prod/checkout", "depends_on") not in found.edges_by_key()
    assert [node.node_id for node in found.nodes] == ["prod/checkout"]


async def test_a_partial_cluster_read_is_degraded_rather_than_failed() -> None:
    """FR-008's other half: the adapter has to *say* it saw part of the estate."""
    cluster = FakeCluster(
        services=[{"metadata": {"name": "checkout", "namespace": "prod"}}],
        failing=frozenset({"endpoints"}),
    )

    found = await KubernetesDiscovery(reader=cluster).discover()

    assert found.health is DiscoveryHealth.DEGRADED
    assert found.reason
    assert [node.node_id for node in found.nodes] == ["prod/checkout"]


async def test_a_cluster_that_cannot_be_read_at_all_reports_failure_not_an_exception() -> None:
    cluster = FakeCluster(failing=frozenset({"services", "workloads", "endpoints"}))

    found = await KubernetesDiscovery(reader=cluster).discover()

    assert found.health is DiscoveryHealth.FAILED
    assert found.empty is True


# --- Mesh and traces ----------------------------------------------------------


async def test_mesh_traffic_below_the_noise_floor_is_not_a_dependency() -> None:
    # A stray health probe or a developer's curl is not an architecture, and a
    # wrong edge is not obviously wrong when you read it.
    mesh = FakeMesh(
        ObservedTraffic("checkout", "payments", requests=MESH_EDGE_MIN_REQUESTS),
        ObservedTraffic("checkout", "scanner", requests=MESH_EDGE_MIN_REQUESTS - 1),
    )

    found = await ServiceMeshDiscovery(reader=mesh).discover()

    assert set(found.edges_by_key()) == {("checkout", "payments", "calls")}
    assert found.edges[0].metadata["requests"] == str(MESH_EDGE_MIN_REQUESTS)


async def test_an_unreadable_mesh_reports_failure_rather_than_an_empty_estate() -> None:
    found = await ServiceMeshDiscovery(reader=FakeMesh(failing=True)).discover()

    assert found.health is DiscoveryHealth.FAILED
    assert "refused" in found.reason


async def test_trace_derived_edges_carry_their_evidence_and_drop_self_calls() -> None:
    traces = FakeTraces(
        ObservedSpanEdge("checkout", "payments", spans=TRACE_EDGE_MIN_SPANS, p95_latency_ms=91.5),
        ObservedSpanEdge("checkout", "checkout", spans=TRACE_EDGE_MIN_SPANS * 10),
        ObservedSpanEdge("checkout", "flaky", spans=TRACE_EDGE_MIN_SPANS - 1),
    )

    found = await TraceDiscovery(reader=traces).discover()

    assert set(found.edges_by_key()) == {("checkout", "payments", "calls")}
    assert found.edges[0].metadata["p95_latency_ms"] == "91.5"
