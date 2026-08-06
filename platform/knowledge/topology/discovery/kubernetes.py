"""Topology from what a cluster declares: services, their workloads, and owners.

The cheapest topology any team has is the one already written down in their
cluster. A Service names a selector, the endpoints behind it name pods, and each
pod's owner references walk up to the ReplicaSet and the Deployment that created
it. Following that chain gives the "what runs this" half of a topology for free,
on the day the adapter is switched on.

It does not give the "what talks to what" half, which is what the mesh and trace
adapters are for. What it does give, and they cannot, is *ownership*: a Deployment
knows which team's labels it carries, and an operator paging the right team at
04:00 is most of the value of a blast radius.

Declared dependencies are read from an annotation, because a cluster is also
where teams already write this down. ``ninjasre.io/depends-on: payments,postgres``
on a Service or a Deployment becomes edges — checked in with the manifest,
reviewed like the manifest, and re-read on every discovery run.

**No Kubernetes client is imported here.** ``platform`` is tier 3 and the vendor
integration is tier 2, so this adapter takes a reader over whatever the
deployment already has. That is also what lets the whole adapter be tested
without a cluster.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from platform.knowledge.topology.discovery.port import DiscoveredTopology, DiscoveryHealth
from platform.knowledge.topology.models import DependencyEdge, DependencyKind, ServiceNode
from platform.observability.logging import get_logger
from platform.persistence.ports.topology_graph import NodeKind

logger = get_logger(__name__)

#: The source name written onto everything this adapter discovers.
SOURCE = "kubernetes"

#: The annotation a team uses to declare a dependency the cluster cannot infer —
#: a database, a third-party API, a queue. Comma-separated, because that is what
#: fits in an annotation and what a manifest reviewer can read.
DEPENDS_ON_ANNOTATION = "ninjasre.io/depends-on"

#: Labels that name the owning team, in the order they are tried. The first two
#: are the recommended Kubernetes labels; the third is what teams that predate
#: them actually use.
OWNER_LABELS: tuple[str, ...] = (
    "app.kubernetes.io/part-of",
    "app.kubernetes.io/owner",
    "team",
)

#: Separates a namespace from a name in a node id. Kubernetes names cannot
#: contain a slash, so the split back is unambiguous.
NAMESPACE_SEPARATOR = "/"


@runtime_checkable
class ClusterReader(Protocol):
    """The three reads this adapter makes of a cluster.

    Each returns objects in the shape the Kubernetes API returns them —
    ``{"metadata": {...}, "spec": {...}}`` — because that is what every client
    already produces, and translating in the integration would mean a second
    translation to keep in agreement with this one.
    """

    async def services(self) -> Sequence[Mapping[str, Any]]:
        """Return the Service objects this reader is scoped to."""

    async def workloads(self) -> Sequence[Mapping[str, Any]]:
        """Return the Deployment, StatefulSet, and DaemonSet objects."""

    async def endpoints(self) -> Sequence[Mapping[str, Any]]:
        """Return the Endpoints objects that tie services to their pods."""


def _metadata(obj: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return an object's metadata, or an empty mapping."""
    found = obj.get("metadata")
    return found if isinstance(found, Mapping) else {}


def _labels(obj: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    """Return an object's labels or annotations, whichever ``key`` names."""
    found = _metadata(obj).get(key)
    return found if isinstance(found, Mapping) else {}


def node_id(obj: Mapping[str, Any]) -> str:
    """Return the graph id for a Kubernetes object: ``namespace/name``.

    Namespaced because a cluster running ``checkout`` in staging and in
    production has two services, and a topology that merged them would report a
    staging outage's blast radius as production's.
    """
    metadata = _metadata(obj)
    name = str(metadata.get("name", "")).strip()
    namespace = str(metadata.get("namespace", "")).strip()
    return f"{namespace}{NAMESPACE_SEPARATOR}{name}" if namespace else name


def owner_of(obj: Mapping[str, Any]) -> str:
    """Return the team a Kubernetes object's labels name, or ``""``."""
    labels = _labels(obj, "labels")
    for label in OWNER_LABELS:
        value = str(labels.get(label, "")).strip()
        if value:
            return value
    return ""


def declared_dependencies(obj: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the dependencies an object's annotation declares."""
    raw = str(_labels(obj, "annotations").get(DEPENDS_ON_ANNOTATION, ""))
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def workload_owner(obj: Mapping[str, Any]) -> str:
    """Return the id of the workload a pod's owner references point at.

    Only ``Deployment``, ``StatefulSet``, and ``DaemonSet`` are followed. A pod's
    immediate owner is usually a ReplicaSet, which is an implementation detail of
    a Deployment and would put a hash-suffixed node in the graph that is gone
    after the next rollout.
    """
    namespace = str(_metadata(obj).get("namespace", "")).strip()
    for reference in _metadata(obj).get("ownerReferences") or ():
        if not isinstance(reference, Mapping):
            continue
        kind = str(reference.get("kind", ""))
        if kind in {"Deployment", "StatefulSet", "DaemonSet"}:
            name = str(reference.get("name", "")).strip()
            return f"{namespace}{NAMESPACE_SEPARATOR}{name}" if namespace else name
    return ""


@dataclass(slots=True)
class KubernetesDiscovery:
    """Topology derived from what a cluster declares about itself."""

    reader: ClusterReader
    cluster: str = ""

    @property
    def name(self) -> str:
        """Return the source name written onto everything this discovers."""
        return SOURCE

    async def discover(self) -> DiscoveredTopology:
        """Return the cluster's declared topology, with the health of the read.

        Each of the three reads is attempted independently, and a failure in one
        degrades the result rather than failing it. Half a cluster's services
        with the endpoints missing is still worth recording — as long as nothing
        downstream mistakes it for the whole cluster, which is what
        ``DEGRADED`` is for.
        """
        services, services_ok = await self._read(self.reader.services, "services")
        workloads, workloads_ok = await self._read(self.reader.workloads, "workloads")
        endpoints, endpoints_ok = await self._read(self.reader.endpoints, "endpoints")

        reads = (services_ok, workloads_ok, endpoints_ok)
        if not any(reads):
            return DiscoveredTopology(
                source=SOURCE,
                health=DiscoveryHealth.FAILED,
                reason="the cluster API could not be read at all",
            )

        nodes: dict[str, ServiceNode] = {}
        edges: dict[tuple[str, str, str], DependencyEdge] = {}

        for service in services:
            self._add_service(nodes, edges, service, kind=NodeKind.SERVICE)
        for workload in workloads:
            self._add_service(nodes, edges, workload, kind=NodeKind.SERVICE)
        for endpoint in endpoints:
            self._add_endpoint(nodes, edges, endpoint)

        if self.cluster:
            nodes.setdefault(
                self.cluster,
                ServiceNode(node_id=self.cluster, kind=NodeKind.CLUSTER, source=SOURCE),
            )

        health = DiscoveryHealth.HEALTHY if all(reads) else DiscoveryHealth.DEGRADED
        return DiscoveredTopology(
            source=SOURCE,
            nodes=tuple(nodes.values()),
            edges=tuple(edges.values()),
            health=health,
            reason="" if all(reads) else "part of the cluster API could not be read",
            covered=tuple(sorted(nodes)),
        )

    async def _read(self, call: Any, what: str) -> tuple[Sequence[Mapping[str, Any]], bool]:
        """Return one read's objects and whether it succeeded.

        A broad ``except`` on purpose. This adapter's contract is that it reports
        health rather than raising, and the readers it is handed are written by
        whoever runs the deployment — narrowing to the exceptions one client
        happens to raise would make the next client's failure an unhandled one.
        """
        try:
            return await call(), True
        except Exception as error:  # noqa: BLE001 — see the docstring
            logger.warning("topology.kubernetes_read_failed", read=what, error=str(error))
            return (), False

    def _add_service(
        self,
        nodes: dict[str, ServiceNode],
        edges: dict[tuple[str, str, str], DependencyEdge],
        obj: Mapping[str, Any],
        *,
        kind: NodeKind,
    ) -> None:
        """Record one object as a node, plus whatever its annotation declares."""
        identifier = node_id(obj)
        if not identifier:
            return

        nodes[identifier] = ServiceNode(
            node_id=identifier,
            kind=kind,
            name=str(_metadata(obj).get("name", identifier)),
            environment=str(_metadata(obj).get("namespace", "")),
            owner=owner_of(obj),
            source=SOURCE,
        )
        if self.cluster:
            _record(
                edges,
                DependencyEdge(
                    from_node_id=identifier,
                    to_node_id=self.cluster,
                    kind=DependencyKind.DEPLOYS_TO,
                    source=SOURCE,
                ),
            )
        for target in declared_dependencies(obj):
            _record(
                edges,
                DependencyEdge(
                    from_node_id=identifier,
                    to_node_id=target,
                    kind=DependencyKind.DEPENDS_ON,
                    source=SOURCE,
                    metadata={"declared_by": DEPENDS_ON_ANNOTATION},
                ),
            )

    def _add_endpoint(
        self,
        nodes: dict[str, ServiceNode],
        edges: dict[tuple[str, str, str], DependencyEdge],
        endpoint: Mapping[str, Any],
    ) -> None:
        """Record the workloads standing behind one Service.

        The Service depends on the workload: if the Deployment is unhealthy the
        Service is, and a blast radius that did not cross this edge would stop at
        the workload and never reach the callers.

        The commonest case draws no edge at all, deliberately. A Service and the
        Deployment behind it are usually named the same thing in the same
        namespace, so they collapse to one node — which is what an operator means
        by "checkout" and what an alert names. An edge is drawn only where the
        two genuinely differ, which is where knowing about the workload actually
        tells the investigation something.
        """
        service = node_id(endpoint)
        if not service:
            return

        nodes.setdefault(
            service, ServiceNode(node_id=service, kind=NodeKind.SERVICE, source=SOURCE)
        )

        for subset in endpoint.get("subsets") or ():
            if not isinstance(subset, Mapping):
                continue
            for address in subset.get("addresses") or ():
                if not isinstance(address, Mapping):
                    continue
                target = address.get("targetRef")
                workload = workload_owner(target) if isinstance(target, Mapping) else ""
                if not workload or workload == service:
                    continue
                nodes.setdefault(
                    workload,
                    ServiceNode(node_id=workload, kind=NodeKind.SERVICE, source=SOURCE),
                )
                _record(
                    edges,
                    DependencyEdge(
                        from_node_id=service,
                        to_node_id=workload,
                        kind=DependencyKind.DEPENDS_ON,
                        source=SOURCE,
                        metadata={"via": "endpoints"},
                    ),
                )


def _record(edges: dict[tuple[str, str, str], DependencyEdge], edge: DependencyEdge) -> None:
    """Store ``edge`` under its key, keeping the first of any duplicates.

    Duplicates are the normal case: a Service with three replicas produces three
    endpoint addresses pointing at one Deployment. Keeping the first is enough
    because they are identical, and doing it here rather than at the call site
    keeps the caller from having to know that.
    """
    edges.setdefault(edge.key, edge)


__all__ = [
    "DEPENDS_ON_ANNOTATION",
    "NAMESPACE_SEPARATOR",
    "OWNER_LABELS",
    "SOURCE",
    "ClusterReader",
    "KubernetesDiscovery",
    "declared_dependencies",
    "node_id",
    "owner_of",
    "workload_owner",
]
