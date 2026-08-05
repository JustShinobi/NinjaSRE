"""Hierarchy and configuration over PostgreSQL."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from platform.persistence.errors import (
    ConcurrentModification,
    DuplicateRecord,
    RecordNotFound,
    ReferencedRecord,
)
from platform.persistence.ports.config_repository import (
    ConfigNode,
    ConfigNodeKind,
    Organisation,
)
from platform.persistence.postgres import models
from platform.persistence.postgres.repositories.common import (
    TenantBound,
    as_utc,
    rows_affected,
    translating,
    utc_now,
)


def _to_node(row: models.ConfigNode) -> ConfigNode:
    return ConfigNode(
        node_id=row.node_id,
        kind=ConfigNodeKind(row.kind),
        name=row.name,
        parent_id=row.parent_id,
        values=dict(row.values),
        version=row.version,
        updated_at=as_utc(row.updated_at),
    )


def _to_org(row: models.Organisation) -> Organisation:
    return Organisation(
        org_id=row.org_id,
        name=row.name,
        created_at=as_utc(row.created_at) or row.created_at,
        is_active=row.is_active,
    )


@dataclass(slots=True)
class PostgresConfigRepository(TenantBound):
    """Hierarchy and configuration for one organisation."""

    async def root(self) -> ConfigNode:
        """Return the organisation node this unit of work is scoped to."""
        node = await self.get(self.org_id)
        if node is None:
            raise RecordNotFound(kind="config node", identifier=self.org_id)
        return node

    async def get(self, node_id: str) -> ConfigNode | None:
        """Return the node with ``node_id``, or ``None`` if this tenant has none."""
        row = await self.session.get(models.ConfigNode, (self.org_id, node_id))
        return _to_node(row) if row is not None else None

    async def upsert(self, node: ConfigNode) -> ConfigNode:
        """Store ``node`` and return it with its new version."""
        row = await self.session.get(models.ConfigNode, (self.org_id, node.node_id))
        if row is not None and row.version != node.version:
            raise ConcurrentModification(
                kind="config node",
                identifier=node.node_id,
                expected=node.version,
                found=row.version,
            )
        if node.parent_id is not None:
            parent = await self.session.get(models.ConfigNode, (self.org_id, node.parent_id))
            if parent is None:
                raise RecordNotFound(kind="config node", identifier=node.parent_id)

        stamped = utc_now()
        if row is None:
            row = models.ConfigNode(org_id=self.org_id, node_id=node.node_id)
            self.session.add(row)
        row.kind = node.kind.value
        row.name = node.name
        row.parent_id = node.parent_id
        row.values = dict(node.values)
        row.version = node.version + 1
        row.updated_at = stamped

        with translating(kind="config node", identifier=node.node_id):
            await self.session.flush()
        return _to_node(row)

    async def children(self, node_id: str) -> tuple[ConfigNode, ...]:
        """Return the direct children of ``node_id``, ordered by name."""
        rows = await self.session.scalars(
            select(models.ConfigNode)
            .where(
                models.ConfigNode.org_id == self.org_id,
                models.ConfigNode.parent_id == node_id,
            )
            .order_by(models.ConfigNode.name, models.ConfigNode.node_id)
        )
        return tuple(_to_node(row) for row in rows)

    async def ancestors(self, node_id: str) -> tuple[ConfigNode, ...]:
        """Return the path from the root down to ``node_id``, inclusive.

        Walked in Python rather than as a recursive CTE. The hierarchy is
        service-topology deep, not tree-of-accounts deep — a handful of levels —
        and a loop of primary-key lookups against a warm cache beats a recursive
        query that has to be read carefully every time somebody changes it.
        """
        path: list[ConfigNode] = []
        seen: set[str] = set()
        current: str | None = node_id

        while current is not None and current not in seen:
            seen.add(current)
            node = await self.get(current)
            if node is None:
                if not path:
                    raise RecordNotFound(kind="config node", identifier=node_id)
                break
            path.append(node)
            current = node.parent_id

        return tuple(reversed(path))

    async def delete(self, node_id: str) -> bool:
        """Delete ``node_id`` and return whether it existed."""
        row = await self.session.get(models.ConfigNode, (self.org_id, node_id))
        if row is None:
            return False

        child = await self.session.scalar(
            select(models.ConfigNode.node_id)
            .where(
                models.ConfigNode.org_id == self.org_id,
                models.ConfigNode.parent_id == node_id,
            )
            .limit(1)
        )
        if child is not None:
            raise ReferencedRecord(
                kind="config node", identifier=node_id, referenced_by=f"child node {child!r}"
            )

        await self.session.delete(row)
        await self.session.flush()
        return True


@dataclass(slots=True)
class PostgresOrgDirectory:
    """Organisation records, across the whole store."""

    session: AsyncSession

    async def create_organisation(self, org_id: str, name: str) -> Organisation:
        """Create the organisation and its root node, and return it."""
        existing = await self.session.get(models.Organisation, org_id)
        if existing is not None:
            raise DuplicateRecord(kind="organisation", identifier=org_id)

        created_at = utc_now()
        row = models.Organisation(org_id=org_id, name=name, created_at=created_at, is_active=True)
        self.session.add(row)

        # Flushed before the node that references it. ``config_nodes`` is
        # self-referential, which puts it in a cycle of its own in SQLAlchemy's
        # table sort and stops the sort from reliably ordering it after
        # ``organisations``. Two flushes in one transaction cost nothing and do
        # not depend on that ordering being what we assumed.
        with translating(kind="organisation", identifier=org_id):
            await self.session.flush()

        # Created with the organisation rather than lazily: a tenant whose
        # hierarchy has no root is one where ``ancestors`` returns a path that
        # starts nowhere, and every caller would have to handle it.
        self.session.add(
            models.ConfigNode(
                org_id=org_id,
                node_id=org_id,
                kind=ConfigNodeKind.ORGANISATION.value,
                name=name,
                parent_id=None,
                values={},
                version=1,
                updated_at=created_at,
            )
        )
        with translating(kind="config node", identifier=org_id):
            await self.session.flush()
        return _to_org(row)

    async def get_organisation(self, org_id: str) -> Organisation | None:
        """Return the organisation with ``org_id``, or ``None``."""
        row = await self.session.get(models.Organisation, org_id)
        return _to_org(row) if row is not None else None

    async def list_organisations(self) -> tuple[Organisation, ...]:
        """Return every organisation, ordered by id."""
        rows = await self.session.scalars(
            select(models.Organisation).order_by(models.Organisation.org_id)
        )
        return tuple(_to_org(row) for row in rows)

    async def delete_organisation(self, org_id: str) -> bool:
        """Remove an organisation and everything cascading from it.

        Not on the port. It exists for the test suite, which creates and drops
        tenants, and for an operator offboarding one — and it deliberately does
        not remove that organisation's audit events, whose foreign key restricts
        rather than cascades (FR-022).
        """
        result = await self.session.execute(
            delete(models.Organisation).where(models.Organisation.org_id == org_id)
        )
        await self.session.flush()
        return bool(rows_affected(result))


__all__ = ["PostgresConfigRepository", "PostgresOrgDirectory"]
