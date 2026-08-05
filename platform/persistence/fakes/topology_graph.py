"""In-memory service topology, with the same bounds the real traversals carry.

Breadth-first everywhere, which is what makes the bounds meaningful: depth is
counted in hops from the origin, so ``MAX_GRAPH_DEPTH`` cuts the frontier rather
than the recursion, and ``MAX_GRAPH_RESULTS`` cuts a level rather than a branch.
A depth-first fake would satisfy the same signatures and truncate a completely
different set of nodes, which is exactly the kind of divergence running one
contract suite against both backends exists to catch.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, replace

from config.constants.persistence import (
    DEFAULT_GRAPH_DEPTH,
    MAX_GRAPH_DEPTH,
    MAX_GRAPH_RESULTS,
)
from platform.persistence.errors import BoundExceeded, TopologyUnavailable
from platform.persistence.fakes.state import State, TenantState
from platform.persistence.ports.topology_graph import (
    BlastRadius,
    BlastRadiusEntry,
    EdgeKind,
    TopologyAvailability,
    TopologyEdge,
    TopologyNode,
    TraversalResult,
)


@dataclass(slots=True)
class FakeTopologyGraph:
    """Topology for one organisation."""

    org_id: str
    state: TenantState
    store: State

    async def availability(self) -> TopologyAvailability:
        """Return whether graph storage is usable right now."""
        if self.store.topology_available:
            return TopologyAvailability(available=True)
        return TopologyAvailability(
            available=False,
            reason=self.store.topology_unavailable_reason,
        )

    async def upsert_node(self, node: TopologyNode) -> TopologyNode:
        """Store ``node``, merging its properties over any existing ones."""
        self._require_available()
        existing = self.state.topology_nodes.get(node.node_id)
        if existing is None:
            self.state.topology_nodes[node.node_id] = node
            return node

        merged = replace(
            node,
            name=node.name or existing.name,
            owner_node_id=node.owner_node_id or existing.owner_node_id,
            properties={**existing.properties, **node.properties},
        )
        self.state.topology_nodes[node.node_id] = merged
        return merged

    async def upsert_edge(self, edge: TopologyEdge) -> TopologyEdge:
        """Store ``edge``, creating either endpoint if the graph lacks it."""
        self._require_available()
        for node_id in (edge.from_node_id, edge.to_node_id):
            if node_id not in self.state.topology_nodes:
                self.state.topology_nodes[node_id] = TopologyNode(node_id=node_id, name=node_id)

        key = (edge.from_node_id, edge.to_node_id, edge.kind.value)
        existing = self.state.topology_edges.get(key)
        merged = (
            edge
            if existing is None
            else replace(edge, properties={**existing.properties, **edge.properties})
        )
        self.state.topology_edges[key] = merged
        return merged

    async def direct_dependencies(self, node_id: str) -> TraversalResult:
        """Return what ``node_id`` depends on, one hop out."""
        self._require_available()
        return self._collect(
            edge.to_node_id for edge in self._dependency_edges() if edge.from_node_id == node_id
        )

    async def direct_dependents(self, node_id: str) -> TraversalResult:
        """Return what depends on ``node_id``, one hop in."""
        self._require_available()
        return self._collect(
            edge.from_node_id for edge in self._dependency_edges() if edge.to_node_id == node_id
        )

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
        _check_depth(depth)

        reached: list[BlastRadiusEntry] = []
        seen = {node_id}
        frontier = deque([(node_id, 0)])
        truncated = False

        while frontier:
            current, distance = frontier.popleft()
            if distance >= depth:
                continue
            for edge in self._dependency_edges():
                if edge.to_node_id != current or edge.from_node_id in seen:
                    continue
                seen.add(edge.from_node_id)
                node = self.state.topology_nodes.get(edge.from_node_id)
                if node is None:
                    continue
                if len(reached) >= MAX_GRAPH_RESULTS:
                    truncated = True
                    frontier.clear()
                    break
                reached.append(BlastRadiusEntry(node=node, depth=distance + 1))
                frontier.append((edge.from_node_id, distance + 1))

        reached.sort(key=lambda entry: (entry.depth, entry.node.node_id))
        return BlastRadius(
            origin_id=node_id,
            max_depth=depth,
            reaches=tuple(reached),
            truncated=truncated,
        )

    async def shortest_path(
        self,
        from_node_id: str,
        to_node_id: str,
    ) -> tuple[TopologyNode, ...]:
        """Return the shortest dependency path between two nodes, or ``()``."""
        self._require_available()
        if from_node_id not in self.state.topology_nodes:
            return ()
        if from_node_id == to_node_id:
            return (self.state.topology_nodes[from_node_id],)

        previous: dict[str, str] = {}
        seen = {from_node_id}
        frontier = deque([(from_node_id, 0)])

        while frontier:
            current, distance = frontier.popleft()
            if distance >= MAX_GRAPH_DEPTH:
                continue
            for edge in self._dependency_edges():
                if edge.from_node_id != current or edge.to_node_id in seen:
                    continue
                seen.add(edge.to_node_id)
                previous[edge.to_node_id] = current
                if edge.to_node_id == to_node_id:
                    return self._path_to(to_node_id, previous)
                frontier.append((edge.to_node_id, distance + 1))

        return ()

    async def components_for_episode(self, episode_id: str) -> TraversalResult:
        """Return the components an episode involved."""
        self._require_available()
        return self._collect(
            edge.to_node_id
            for edge in self.state.topology_edges.values()
            if edge.kind is EdgeKind.INVOLVED and edge.from_node_id == episode_id
        )

    async def episodes_for_component(self, node_id: str) -> TraversalResult:
        """Return the episodes that involved ``node_id``, ordered by id."""
        self._require_available()
        return self._collect(
            edge.from_node_id
            for edge in self.state.topology_edges.values()
            if edge.kind is EdgeKind.INVOLVED and edge.to_node_id == node_id
        )

    def _dependency_edges(self) -> tuple[TopologyEdge, ...]:
        """Return every edge that expresses a dependency.

        ``INVOLVED`` is excluded. An episode is attached to the components it
        touched, and letting a traversal cross that edge would make every
        service that ever appeared in an incident a dependent of every other
        one that did.
        """
        return tuple(
            edge
            for edge in self.state.topology_edges.values()
            if edge.kind is not EdgeKind.INVOLVED
        )

    def _collect(self, node_ids: Iterable[str]) -> TraversalResult:
        """Return the named nodes, deduplicated, ordered, and bounded by result size."""
        found: dict[str, TopologyNode] = {}
        truncated = False

        for node_id in node_ids:
            if node_id in found:
                continue
            node = self.state.topology_nodes.get(node_id)
            if node is None:
                continue
            if len(found) >= MAX_GRAPH_RESULTS:
                truncated = True
                break
            found[node_id] = node

        return TraversalResult(
            nodes=tuple(found[key] for key in sorted(found)),
            truncated=truncated,
        )

    def _path_to(self, target: str, previous: dict[str, str]) -> tuple[TopologyNode, ...]:
        """Return the node path ending at ``target``, walked back through ``previous``."""
        path = [target]
        while path[-1] in previous:
            path.append(previous[path[-1]])
        return tuple(self.state.topology_nodes[node_id] for node_id in reversed(path))

    def _require_available(self) -> None:
        if not self.store.topology_available:
            raise TopologyUnavailable(self.store.topology_unavailable_reason)


def _check_depth(depth: int) -> int:
    """Return ``depth``, or raise if it exceeds the traversal bound."""
    if depth > MAX_GRAPH_DEPTH:
        raise BoundExceeded(
            parameter="depth",
            requested=depth,
            limit=MAX_GRAPH_DEPTH,
            constant="MAX_GRAPH_DEPTH",
        )
    if depth < 1:
        raise ValueError(f"A traversal must cross at least one hop, got {depth}.")
    return depth


__all__ = ["FakeTopologyGraph"]
