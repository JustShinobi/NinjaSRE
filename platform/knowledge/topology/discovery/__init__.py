"""Adapters that observe a running estate and report what they saw.

Three of them ship, and they see genuinely different things — which is why there
are three rather than one with options. A Kubernetes API knows what is *declared*:
services, the workloads behind them, and the owner references linking the two. A
service mesh knows what actually *talks*, including the dependency nobody wrote
down. Traces know what talks **within one request**, which is the only source that
distinguishes "these two services communicate" from "this service is on the
critical path of that user's checkout".

Every adapter reports its **health** alongside its findings, and that is the field
the whole package is arranged around. A source that saw the estate and a source
that saw a third of it before the API server timed out return the same shape, and
reconciliation treats them completely differently: the first removes what it did
not see, the second removes nothing. Without the health signal, one bad minute in
a control plane deletes a team's topology.

No adapter here imports a vendor client. ``platform`` is tier 3 and integrations
are tier 2, so each adapter takes a *reader* — a small protocol over whatever the
deployment already has — and turns what it returns into nodes and edges. That is
also what makes them testable without a cluster.
"""

from __future__ import annotations

from platform.knowledge.topology.discovery.kubernetes import (
    ClusterReader,
    KubernetesDiscovery,
)
from platform.knowledge.topology.discovery.mesh import (
    MeshTelemetryReader,
    ObservedTraffic,
    ServiceMeshDiscovery,
)
from platform.knowledge.topology.discovery.port import (
    DiscoveredTopology,
    DiscoveryHealth,
    DiscoverySource,
)
from platform.knowledge.topology.discovery.traces import (
    ObservedSpanEdge,
    TraceDiscovery,
    TraceReader,
)

__all__ = [
    "ClusterReader",
    "DiscoveredTopology",
    "DiscoveryHealth",
    "DiscoverySource",
    "KubernetesDiscovery",
    "MeshTelemetryReader",
    "ObservedSpanEdge",
    "ObservedTraffic",
    "ServiceMeshDiscovery",
    "TraceDiscovery",
    "TraceReader",
]
