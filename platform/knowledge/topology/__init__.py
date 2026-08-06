"""Service topology: bounded traversals, declarative import, and reconciliation.

Everything here sits on the ``TopologyGraph`` port's closed catalogue. No module
in this package builds a query, because there is no way to hand that port one —
which is what makes "an LLM-generated graph query is never executed" a property
of the signatures rather than a rule somebody has to remember.

The package divides in three:

- ``models`` — the domain records and their translation to the stored shapes.
- ``queries`` — the read path: bounded, cycle-safe, and degrading visibly when
  the graph cannot answer.
- ``write``, ``import_``, ``discovery/``, ``reconciliation`` — the write path: an
  operator typing a dependency, a file they wrote, adapters that observe a
  running estate, and the three-way merge that lets the last of those run again
  without destroying the first two.
"""

from __future__ import annotations

from platform.knowledge.topology.discovery import (
    DiscoveredTopology,
    DiscoveryHealth,
    DiscoverySource,
    KubernetesDiscovery,
    ServiceMeshDiscovery,
    TraceDiscovery,
)
from platform.knowledge.topology.import_ import (
    TopologyDocument,
    TopologyImporter,
    parse_topology,
)
from platform.knowledge.topology.models import (
    BlastRadius,
    DependencyEdge,
    DependencyKind,
    DependencySet,
    ReachedService,
    ServiceNode,
)
from platform.knowledge.topology.queries import (
    ServiceTopology,
    TopologyLedger,
    TopologyQueries,
    TopologyRecord,
)
from platform.knowledge.topology.reconciliation import Reconciliation, TopologyReconciler
from platform.knowledge.topology.write import TopologyWriter, TopologyWriteReport

__all__ = [
    "BlastRadius",
    "DependencyEdge",
    "DependencyKind",
    "DependencySet",
    "DiscoveredTopology",
    "DiscoveryHealth",
    "DiscoverySource",
    "KubernetesDiscovery",
    "ReachedService",
    "Reconciliation",
    "ServiceMeshDiscovery",
    "ServiceNode",
    "ServiceTopology",
    "TopologyDocument",
    "TopologyImporter",
    "TopologyLedger",
    "TopologyQueries",
    "TopologyReconciler",
    "TopologyRecord",
    "TopologyWriteReport",
    "TopologyWriter",
    "TraceDiscovery",
    "parse_topology",
]
