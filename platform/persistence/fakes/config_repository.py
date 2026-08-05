"""In-memory hierarchy and configuration."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from platform.persistence.errors import (
    ConcurrentModification,
    DuplicateRecord,
    RecordNotFound,
    ReferencedRecord,
)
from platform.persistence.fakes.state import State, TenantState
from platform.persistence.ports.config_repository import (
    ConfigNode,
    ConfigNodeKind,
    Organisation,
)

# An organisation's root node carries the organisation's own id. One less
# identifier to correlate, and ``ancestors`` terminating at ``parent_id is
# None`` then needs no special case for the root.


@dataclass(slots=True)
class FakeConfigRepository:
    """Hierarchy and configuration for one organisation."""

    org_id: str
    state: TenantState

    async def root(self) -> ConfigNode:
        """Return the organisation node this unit of work is scoped to."""
        node = self.state.config_nodes.get(self.org_id)
        if node is None:
            raise RecordNotFound(kind="config node", identifier=self.org_id)
        return node

    async def get(self, node_id: str) -> ConfigNode | None:
        """Return the node with ``node_id``, or ``None`` if this tenant has none."""
        return self.state.config_nodes.get(node_id)

    async def upsert(self, node: ConfigNode) -> ConfigNode:
        """Store ``node`` and return it with its new version."""
        existing = self.state.config_nodes.get(node.node_id)
        if existing is not None and existing.version != node.version:
            raise ConcurrentModification(
                kind="config node",
                identifier=node.node_id,
                expected=node.version,
                found=existing.version,
            )
        if node.parent_id is not None and node.parent_id not in self.state.config_nodes:
            raise RecordNotFound(kind="config node", identifier=node.parent_id)

        stored = replace(node, version=node.version + 1, updated_at=datetime.now(UTC))
        self.state.config_nodes[node.node_id] = stored
        return stored

    async def children(self, node_id: str) -> tuple[ConfigNode, ...]:
        """Return the direct children of ``node_id``, ordered by name."""
        found = [n for n in self.state.config_nodes.values() if n.parent_id == node_id]
        return tuple(sorted(found, key=lambda n: (n.name, n.node_id)))

    async def ancestors(self, node_id: str) -> tuple[ConfigNode, ...]:
        """Return the path from the root down to ``node_id``, inclusive."""
        path: list[ConfigNode] = []
        seen: set[str] = set()
        current: str | None = node_id

        while current is not None and current not in seen:
            seen.add(current)
            node = self.state.config_nodes.get(current)
            if node is None:
                if not path:
                    raise RecordNotFound(kind="config node", identifier=node_id)
                break
            path.append(node)
            current = node.parent_id

        return tuple(reversed(path))

    async def delete(self, node_id: str) -> bool:
        """Delete ``node_id`` and return whether it existed."""
        if node_id not in self.state.config_nodes:
            return False
        child = next(
            (n for n in self.state.config_nodes.values() if n.parent_id == node_id),
            None,
        )
        if child is not None:
            raise ReferencedRecord(
                kind="config node",
                identifier=node_id,
                referenced_by=f"child node {child.node_id!r}",
            )
        del self.state.config_nodes[node_id]
        return True


@dataclass(slots=True)
class FakeOrgDirectory:
    """Organisation records, across the whole store."""

    state: State

    async def create_organisation(self, org_id: str, name: str) -> Organisation:
        """Create the organisation and its root node, and return it."""
        if org_id in self.state.organisations:
            raise DuplicateRecord(kind="organisation", identifier=org_id)

        created_at = datetime.now(UTC)
        organisation = Organisation(org_id=org_id, name=name, created_at=created_at)
        self.state.organisations[org_id] = organisation

        # The root node is created with the organisation rather than lazily. A
        # tenant whose hierarchy has no root is one where ``ancestors`` returns
        # a path that starts nowhere, and every caller would need to handle it.
        self.state.tenant(org_id).config_nodes[org_id] = ConfigNode(
            node_id=org_id,
            kind=ConfigNodeKind.ORGANISATION,
            name=name,
            version=1,
            updated_at=created_at,
        )
        return organisation

    async def get_organisation(self, org_id: str) -> Organisation | None:
        """Return the organisation with ``org_id``, or ``None``."""
        return self.state.organisations.get(org_id)

    async def list_organisations(self) -> tuple[Organisation, ...]:
        """Return every organisation, ordered by id."""
        return tuple(self.state.organisations[key] for key in sorted(self.state.organisations))


__all__ = ["FakeConfigRepository", "FakeOrgDirectory"]
