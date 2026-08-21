"""Service topology over Apache AGE.

Every method here runs one of the pre-rendered statements in ``graph.queries``
and passes its values as agtype parameters. No caller string reaches a query.

Tenancy is the one thing AGE cannot give us structurally: it has one graph per
database, not one per organisation, and creating a graph per tenant would mean
DDL on every onboarding and a name to validate on every query. So every node id
is *prefixed with the organisation* on the way in and stripped on the way out.
The prefix is applied here, in one place, from ``self.org_id`` — which the unit
of work supplied and a caller cannot reach — so a traversal physically cannot
leave its tenant's subgraph: the neighbouring nodes it would have to walk to are
named differently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config.constants.persistence import DEFAULT_GRAPH_DEPTH, MAX_GRAPH_DEPTH, MAX_GRAPH_RESULTS
from platform.persistence.errors import TopologyUnavailable
from platform.persistence.ports.topology_graph import (
    BlastRadius,
    BlastRadiusEntry,
    EdgeKind,
    NodeKind,
    TopologyAvailability,
    TopologyEdge,
    TopologyNode,
    TraversalResult,
)
from platform.persistence.postgres.graph import agtype, bootstrap, queries
from platform.persistence.postgres.repositories.common import TenantBound

#: Separates the organisation from the caller's node id. A colon cannot appear
#: in an organisation id — ``identifiers.safe_identifier`` would reject it — so
#: the split back is unambiguous.
TENANT_SEPARATOR = "\x1f"


@dataclass(slots=True)
class PostgresTopologyGraph(TenantBound):
    """Topology for one organisation, over the single AGE graph."""

    readiness: bootstrap.GraphReadiness

    async def availability(self) -> TopologyAvailability:
        """Return whether graph storage is usable right now (FR-002)."""
        return TopologyAvailability(
            available=self.readiness.available,
            reason=self.readiness.reason,
        )

    async def upsert_node(self, node: TopologyNode) -> TopologyNode:
        """Store ``node``, merging its properties over any existing ones."""
        self._require_available()
        existing = await self._read_node(node.node_id)

        # Merge rather than replace: topology arrives from several discovery
        # sources, and a Kubernetes scraper that learns a namespace must not
        # erase the owner a config sync recorded.
        merged = TopologyNode(
            node_id=node.node_id,
            kind=node.kind if existing is None else (node.kind or existing.kind),
            name=node.name or (existing.name if existing else ""),
            owner_node_id=node.owner_node_id or (existing.owner_node_id if existing else None),
            properties={**(existing.properties if existing else {}), **node.properties},
        )

        await self._run(
            queries.UPSERT_NODE,
            {
                "node_id": self._scoped(merged.node_id),
                "kind": merged.kind.value,
                "name": merged.name,
                "owner_node_id": merged.owner_node_id or "",
                "properties": agtype.encode_properties(dict(merged.properties)),
            },
        )
        return merged

    async def upsert_edge(self, edge: TopologyEdge) -> TopologyEdge:
        """Store ``edge``, creating either endpoint if the graph lacks it."""
        self._require_available()
        existing = await self._read_edge(edge)
        merged = TopologyEdge(
            from_node_id=edge.from_node_id,
            to_node_id=edge.to_node_id,
            kind=edge.kind,
            properties={**(existing or {}), **edge.properties},
        )

        await self._run(
            queries.UPSERT_EDGE,
            {
                "from_node_id": self._scoped(edge.from_node_id),
                "to_node_id": self._scoped(edge.to_node_id),
                "kind": edge.kind.value,
                "properties": agtype.encode_properties(dict(merged.properties)),
            },
        )
        return merged

    async def edges_from(self, node_id: str) -> tuple[TopologyEdge, ...]:
        """Return the edges leaving ``node_id``, with their stored properties."""
        self._require_available()
        rows = await self._run(queries.EDGES_FROM, {"node_id": self._scoped(node_id)})
        return tuple(
            TopologyEdge(
                from_node_id=node_id,
                to_node_id=self._unscoped(str(agtype.loads(raw_target))),
                kind=EdgeKind(str(agtype.loads(raw_kind))),
                properties=agtype.decode_properties(agtype.loads(raw_properties)),
            )
            for raw_target, raw_kind, raw_properties in rows
        )

    async def delete_edge(self, edge: TopologyEdge) -> bool:
        """Delete one edge and return whether it existed. Endpoints are kept."""
        self._require_available()
        rows = await self._run(
            queries.DELETE_EDGE,
            {
                "from_node_id": self._scoped(edge.from_node_id),
                "to_node_id": self._scoped(edge.to_node_id),
                "kind": edge.kind.value,
            },
        )
        return bool(rows)

    async def direct_dependencies(self, node_id: str) -> TraversalResult:
        """Return what ``node_id`` depends on, one hop out."""
        return await self._nodes(queries.DIRECT_DEPENDENCIES, node_id)

    async def direct_dependents(self, node_id: str) -> TraversalResult:
        """Return what depends on ``node_id``, one hop in."""
        return await self._nodes(queries.DIRECT_DEPENDENTS, node_id)

    async def transitive_dependents(
        self,
        node_id: str,
        *,
        depth: int = DEFAULT_GRAPH_DEPTH,
    ) -> TraversalResult:
        """Return everything that depends on ``node_id`` within ``depth`` hops."""
        radius = await self.blast_radius(node_id, depth=depth)
        return TraversalResult(
            nodes=tuple(entry.node for entry in radius.reaches),
            truncated=radius.truncated,
        )

    async def blast_radius(
        self,
        node_id: str,
        *,
        depth: int = DEFAULT_GRAPH_DEPTH,
    ) -> BlastRadius:
        """Return what an outage at ``node_id`` would reach, with hop distances."""
        self._require_available()
        rows = await self._run(queries.blast_radius(depth), {"node_id": self._scoped(node_id)})

        # A variable-length match returns one row per path, so a node reachable
        # by two routes appears twice. The nearest hop count is the one that
        # matters — it is how soon the failure arrives.
        nearest: dict[str, BlastRadiusEntry] = {}
        for raw_node, raw_hops in rows:
            node = self._to_node(agtype.properties_of(raw_node))
            hops = agtype.as_int(raw_hops)
            seen = nearest.get(node.node_id)
            if seen is None or hops < seen.depth:
                nearest[node.node_id] = BlastRadiusEntry(node=node, depth=hops)

        entries = sorted(nearest.values(), key=lambda entry: (entry.depth, entry.node.node_id))
        return BlastRadius(
            origin_id=node_id,
            max_depth=depth,
            reaches=tuple(entries[:MAX_GRAPH_RESULTS]),
            truncated=len(entries) > MAX_GRAPH_RESULTS,
        )

    async def shortest_path(
        self,
        from_node_id: str,
        to_node_id: str,
    ) -> tuple[TopologyNode, ...]:
        """Return the shortest dependency path between two nodes, or ``()``."""
        self._require_available()
        if from_node_id == to_node_id:
            node = await self._read_node(from_node_id)
            return (node,) if node is not None else ()

        rows = await self._run(
            queries.shortest_path(MAX_GRAPH_DEPTH),
            {
                "from_node_id": self._scoped(from_node_id),
                "to_node_id": self._scoped(to_node_id),
            },
        )
        if not rows:
            return ()

        raw_path, _ = rows[0]
        vertices = agtype.loads(raw_path) or []
        return tuple(
            self._to_node(dict(vertex.get("properties", {})))
            for vertex in vertices
            if isinstance(vertex, dict)
        )

    async def components_for_episode(self, episode_id: str) -> TraversalResult:
        """Return the components an episode involved."""
        return await self._nodes(queries.COMPONENTS_FOR_EPISODE, episode_id)

    async def episodes_for_component(self, node_id: str) -> TraversalResult:
        """Return the episodes that involved ``node_id``, ordered by id."""
        return await self._nodes(queries.EPISODES_FOR_COMPONENT, node_id)

    # --- internals ------------------------------------------------------------

    def _scoped(self, node_id: str) -> str:
        """Return ``node_id`` namespaced to this unit of work's organisation."""
        return f"{self.org_id}{TENANT_SEPARATOR}{node_id}"

    def _unscoped(self, node_id: str) -> str:
        """Return the caller's own id from a namespaced one."""
        prefix = f"{self.org_id}{TENANT_SEPARATOR}"
        return node_id[len(prefix) :] if node_id.startswith(prefix) else node_id

    def _require_available(self) -> None:
        if not self.readiness.available:
            raise TopologyUnavailable(self.readiness.reason or "graph storage is unavailable")

    async def _run(self, statement: str, parameters: dict[str, Any]) -> list[Any]:
        """Run one catalogue statement with agtype parameters.

        Executed on the driver connection rather than through ``text()``, and
        the reason is specific: Cypher's label syntax is ``(n:Node)``, and
        SQLAlchemy reads ``:Node`` as a bind parameter it has never been given.
        Escaping every colon in every query would work and would be one missed
        backslash away from a statement that fails at runtime.

        This is the same connection and the same transaction the rest of the
        unit of work uses — the session hands it over — so a graph write still
        commits and rolls back with everything beside it.
        """
        connection = await self.session.connection()
        raw = await connection.get_raw_connection()
        driver = raw.driver_connection
        if driver is None:  # pragma: no cover — a live connection always has one
            raise TopologyUnavailable("the database connection has no driver attached")

        rows = await driver.fetch(statement, agtype.encode_properties(parameters))
        return [tuple(row) for row in rows]

    async def _nodes(self, statement: str, node_id: str) -> TraversalResult:
        self._require_available()
        rows = await self._run(statement, {"node_id": self._scoped(node_id)})

        found: dict[str, TopologyNode] = {}
        for (raw,) in rows:
            node = self._to_node(agtype.properties_of(raw))
            found.setdefault(node.node_id, node)

        ordered = tuple(found[key] for key in sorted(found))
        return TraversalResult(
            nodes=ordered[:MAX_GRAPH_RESULTS],
            truncated=len(ordered) > MAX_GRAPH_RESULTS,
        )

    def _to_node(self, properties: dict[str, Any]) -> TopologyNode:
        owner = properties.get("owner_node_id") or None
        return TopologyNode(
            node_id=self._unscoped(str(properties.get("node_id", ""))),
            kind=NodeKind(properties.get("kind", NodeKind.SERVICE.value)),
            name=str(properties.get("name", "")),
            owner_node_id=self._unscoped(owner) if owner else None,
            properties=agtype.decode_properties(properties.get("properties")),
        )

    async def _read_node(self, node_id: str) -> TopologyNode | None:
        rows = await self._run(queries.READ_NODE, {"node_id": self._scoped(node_id)})
        if not rows:
            return None
        return self._to_node(agtype.properties_of(rows[0][0]))

    async def _read_edge(self, edge: TopologyEdge) -> dict[str, Any] | None:
        rows = await self._run(
            queries.READ_EDGE,
            {
                "from_node_id": self._scoped(edge.from_node_id),
                "to_node_id": self._scoped(edge.to_node_id),
                "kind": edge.kind.value,
            },
        )
        if not rows:
            return None
        return agtype.decode_properties(agtype.loads(rows[0][0]))


def edge_kinds() -> tuple[str, ...]:
    """Return every edge kind, for the contract suite's catalogue assertion."""
    return tuple(kind.value for kind in EdgeKind)


__all__ = ["TENANT_SEPARATOR", "PostgresTopologyGraph", "edge_kinds"]
