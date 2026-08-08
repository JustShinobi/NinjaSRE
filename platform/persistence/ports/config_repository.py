"""The hierarchy every other record hangs off, and the config layered onto it.

An organisation owns a tree of nodes — teams, services, environments — and each
node carries its own configuration values. Effective configuration for a node is
the deep merge of its ancestors' values with its own, which is why ``ancestors``
returns root-first: that is the order the merge consumes, and computing it here
means feature 013 never has to walk the tree itself.

The tree is also what tenancy is defined against. A ``TenantScope`` names an
organisation and optionally a node within it, and every tenant-scoped port takes
its organisation from that scope rather than from an argument. There is
therefore no way for a caller to ask this repository about another tenant's
configuration — not because a check rejects it, but because the question cannot
be phrased (FR-010).

Creating an organisation is the one operation that cannot be tenant-scoped: at
that moment there is no tenant to scope to. It lives on ``OrgDirectory``, which
is reached only through the system unit of work, and that separation is the
whole reason the cross-tenant surface stays enumerable.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class ConfigNodeKind(StrEnum):
    """What a node in the hierarchy represents.

    One tree rather than one table per level. A deployment that groups by
    region and another that groups by business unit both fit, and neither
    needed a schema change to do it.
    """

    ORGANISATION = "organisation"
    TEAM = "team"
    SERVICE = "service"
    ENVIRONMENT = "environment"


@dataclass(frozen=True, slots=True)
class Organisation:
    """A tenant. The root of one hierarchy and the boundary of every query."""

    org_id: str
    name: str
    created_at: datetime
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class ConfigNode:
    """One node of the hierarchy, with the configuration set at that level.

    ``version`` is optimistic-concurrency control, not a changelog. A write
    carrying a stale version is refused with ``ConcurrentModification`` rather
    than merged, because two operators editing the same node have made a
    decision the store is not entitled to make for them.
    """

    node_id: str
    kind: ConfigNodeKind
    name: str
    parent_id: str | None = None
    values: Mapping[str, Any] = field(default_factory=dict)
    version: int = 0
    updated_at: datetime | None = None


@runtime_checkable
class ConfigRepository(Protocol):
    """The hierarchy and its configuration, within one tenant."""

    async def root(self) -> ConfigNode:
        """Return the organisation node this unit of work is scoped to."""

    async def get(self, node_id: str) -> ConfigNode | None:
        """Return the node with ``node_id``, or ``None`` if this tenant has none."""

    async def upsert(self, node: ConfigNode) -> ConfigNode:
        """Store ``node`` and return it with its new version.

        Raises ``ConcurrentModification`` when the stored version has moved on
        from the one ``node`` carries, and ``RecordNotFound`` when its parent
        does not exist in this tenant.
        """

    async def children(self, node_id: str) -> tuple[ConfigNode, ...]:
        """Return the direct children of ``node_id``, ordered by name."""

    async def ancestors(self, node_id: str) -> tuple[ConfigNode, ...]:
        """Return the path from the root down to ``node_id``, inclusive.

        Root-first, because that is the order a deep merge applies: the most
        general values first, each descendant overriding what it names.
        """

    async def delete(self, node_id: str) -> bool:
        """Delete ``node_id`` and return whether it existed.

        Raises ``ReferencedRecord`` if the node still has children. A
        cascade here would silently drop the configuration of every service
        beneath a team somebody meant to rename.
        """


@runtime_checkable
class OrgDirectory(Protocol):
    """Organisation records, reached only through the system unit of work.

    Three operations, all of which exist because they precede tenancy: you
    cannot scope to an organisation you are about to create, nor list the
    organisations from inside one of them.
    """

    async def create_organisation(self, org_id: str, name: str) -> Organisation:
        """Create the organisation and its root node, and return it.

        Raises ``DuplicateRecord`` if ``org_id`` is already taken.
        """

    async def get_organisation(self, org_id: str) -> Organisation | None:
        """Return the organisation with ``org_id``, or ``None``."""

    async def list_organisations(self) -> tuple[Organisation, ...]:
        """Return every organisation, ordered by id."""

    async def delete_organisation(self, org_id: str) -> bool:
        """Remove an organisation and everything cascading from it.

        Returns whether it existed. On the port because offboarding a tenant is
        an operation a deployment performs — demo mode's one-action removal is
        exactly this, and expressing it as a sweep of thirteen repositories
        instead would be thirteen chances to miss a table.

        It does **not** remove that organisation's audit events: the audit
        foreign key restricts rather than cascades, deliberately, so a tenant
        with audit history cannot be deleted at all. That is the constraint that
        keeps the audit trail append-only, and it is why nothing that has to be
        removable may be written to it.
        """


__all__ = [
    "ConfigNode",
    "ConfigNodeKind",
    "ConfigRepository",
    "OrgDirectory",
    "Organisation",
]
