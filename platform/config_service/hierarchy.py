"""The tree, as a value: ancestry, descendants, and the two writes it refuses.

The repository already answers ``ancestors`` and ``children`` per node, and the
resolution path uses those directly — one indexed read beats materialising a
tree. This module is for the operations that need the *whole* shape at once:
checking a deletion, checking a reparent, and answering "which of my
descendants already override this field" when somebody adds a lock (FR-009).

Two refusals, and both are about a hierarchy that can still be merged
afterwards.

**A node with descendants is not deleted** (FR-004). Cascading would silently
drop the configuration of every service beneath a team somebody meant to
rename, and the loss is invisible until the next investigation resolves to
defaults nobody chose.

**A reparent that would make a node its own ancestor is refused.** A cycle in
the chain is a merge that never terminates, and the place to find out is the
write rather than the next incident.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace

from config.constants.config_service import MAX_HIERARCHY_DEPTH
from platform.config_service.document import NodeDocument
from platform.config_service.errors import (
    HierarchyCycle,
    HierarchyTooDeep,
    NodeHasDescendants,
    UnknownNode,
)
from platform.config_service.merge import Layer
from platform.persistence.ports import ConfigNode


@dataclass(frozen=True, slots=True)
class Hierarchy:
    """One tenant's whole tree, validated on construction.

    Constructing one is the validation: a missing parent, a second root, or a
    tree deeper than the bound raises here rather than surfacing as a merge that
    quietly skipped a level.
    """

    nodes: Mapping[str, ConfigNode] = field(default_factory=dict)

    @classmethod
    def of(cls, nodes: Iterable[ConfigNode]) -> Hierarchy:
        """Return the hierarchy ``nodes`` describes, or raise saying why not."""
        indexed = {node.node_id: node for node in nodes}
        hierarchy = cls(nodes=indexed)
        hierarchy._validate()
        return hierarchy

    def node(self, node_id: str) -> ConfigNode:
        """Return the node with ``node_id``, or raise naming it."""
        found = self.nodes.get(node_id)
        if found is None:
            raise UnknownNode(node_id)
        return found

    def root(self) -> ConfigNode:
        """Return the node with no parent."""
        for node in self.nodes.values():
            if node.parent_id is None:
                return node
        raise HierarchyCycle("This hierarchy has no root: every node names a parent.")

    def chain(self, node_id: str) -> tuple[ConfigNode, ...]:
        """Return the path from the root down to ``node_id``, inclusive.

        Root-first, because that is the order a deep merge applies.
        """
        found: list[ConfigNode] = []
        current: str | None = node_id
        while current is not None:
            node = self.node(current)
            found.append(node)
            current = node.parent_id
            if len(found) > MAX_HIERARCHY_DEPTH:
                raise HierarchyTooDeep(len(found), MAX_HIERARCHY_DEPTH)
        return tuple(reversed(found))

    def children(self, node_id: str) -> tuple[ConfigNode, ...]:
        """Return the direct children of ``node_id``, ordered by name."""
        self.node(node_id)
        found = [node for node in self.nodes.values() if node.parent_id == node_id]
        return tuple(sorted(found, key=lambda node: (node.name, node.node_id)))

    def descendants(self, node_id: str) -> tuple[ConfigNode, ...]:
        """Return every node beneath ``node_id``, breadth-first and name-ordered."""
        found: list[ConfigNode] = []
        frontier = list(self.children(node_id))
        while frontier:
            node = frontier.pop(0)
            found.append(node)
            frontier.extend(self.children(node.node_id))
        return tuple(found)

    def depth(self, node_id: str) -> int:
        """Return how many levels ``node_id`` sits below the root."""
        return len(self.chain(node_id)) - 1

    def layers(self, node_id: str) -> tuple[Layer, ...]:
        """Return the merge layers for ``node_id``'s chain, root-first."""
        return tuple(
            NodeDocument.of_node(node).as_layer(node.node_id) for node in self.chain(node_id)
        )

    def check_deletable(self, node_id: str) -> None:
        """Raise unless ``node_id`` can be deleted without orphaning anything."""
        beneath = self.descendants(node_id)
        if beneath:
            raise NodeHasDescendants(node_id, [node.node_id for node in beneath])

    def reparent(self, node_id: str, new_parent_id: str) -> Hierarchy:
        """Return this hierarchy with ``node_id`` moved under ``new_parent_id``.

        Refuses the root, a self-parent, and any move under the node's own
        descendant — the three shapes that produce a chain with no end.
        """
        node = self.node(node_id)
        self.node(new_parent_id)

        if node.parent_id is None:
            raise HierarchyCycle(f"{node_id!r} is the organisation root and cannot be reparented.")
        if node_id == new_parent_id:
            raise HierarchyCycle(f"{node_id!r} cannot be its own parent.")
        if any(beneath.node_id == new_parent_id for beneath in self.descendants(node_id)):
            raise HierarchyCycle(
                f"Moving {node_id!r} under {new_parent_id!r} would make it its own ancestor."
            )

        moved = dict(self.nodes)
        moved[node_id] = replace(node, parent_id=new_parent_id)
        return Hierarchy.of(moved.values())

    def _validate(self) -> None:
        """Raise unless this is one rooted tree no deeper than the bound."""
        roots = [node for node in self.nodes.values() if node.parent_id is None]
        for node in self.nodes.values():
            if node.parent_id is not None and node.parent_id not in self.nodes:
                raise UnknownNode(node.parent_id)
        if self.nodes and not roots:
            raise HierarchyCycle("This hierarchy has no root: every node names a parent.")
        if len(roots) > 1:
            listed = ", ".join(sorted(node.node_id for node in roots))
            raise HierarchyCycle(
                f"A hierarchy has one root and this one has {len(roots)} ({listed}). "
                f"Separate organisations are separate tenants."
            )
        for node in self.nodes.values():
            self.chain(node.node_id)


__all__ = ["Hierarchy"]
