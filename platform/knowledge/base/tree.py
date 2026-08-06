"""The hierarchy: a view for humans, over a corpus search reads flat.

The tree is what an operator navigates — "the payments team's runbooks, under
recovery" — and it is deliberately *not* what search respects. Search spans the
whole team's corpus (FR-012), because an agent that had to know which folder a
runbook was filed in would be an agent that never finds the one that was filed
somewhere reasonable but unexpected.

That is why the hierarchy is derived rather than stored as a structure. Each
document names its parent; the tree is built on demand from those. Storing the
shape as well would be storing a second thing to keep in agreement with the
first, and the two disagreeing produces a document that exists in a listing and
nowhere in the tree.

Three malformed shapes are handled rather than refused, because a corpus assembled
by four sync adapters over two years will contain all three:

- a parent that does not exist, or belongs to another team — the child becomes a
  root, and is visible rather than lost;
- a cycle — broken at the point it closes, with the members kept as roots;
- a tree deeper than ``MAX_KNOWLEDGE_TREE_DEPTH`` — the deeper documents become
  roots, because past that depth the tree is being used as a filesystem.

Losing a document from the listing is the one outcome none of these may produce.
A document nobody can see is one nobody can fix.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace

from config.constants.knowledge import MAX_KNOWLEDGE_TREE_DEPTH
from config.constants.persistence import MAX_QUERY_PAGE_SIZE
from platform.knowledge.base.models import Document, TreeNode
from platform.observability.logging import get_logger
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope

logger = get_logger(__name__)


def build_tree(documents: Sequence[Document]) -> tuple[TreeNode, ...]:
    """Return ``documents`` as a forest, roots first, in title order.

    Every document appears exactly once, whatever its ``parent_id`` says. That
    is the invariant worth stating: a malformed hierarchy costs the *shape*, not
    the document.
    """
    by_id = {document.document_id: document for document in documents}
    parents = {document.document_id: _resolved_parent(document, by_id) for document in documents}
    children: dict[str, list[str]] = {identifier: [] for identifier in by_id}
    roots: list[str] = []

    for identifier, parent in parents.items():
        if parent is None:
            roots.append(identifier)
        else:
            children[parent].append(identifier)

    ordered = sorted(roots, key=lambda identifier: by_id[identifier].title)
    return tuple(_node(identifier, by_id, children, depth=1) for identifier in ordered)


def _resolved_parent(document: Document, by_id: Mapping[str, Document]) -> str | None:
    """Return the parent a document may actually hang from, or ``None``.

    ``None`` for a root, for a parent nobody holds, for a parent in another team,
    and for a document that is part of a cycle — which is broken here, at the
    point it closes, rather than discovered later by a recursion that does not
    return.
    """
    parent = document.parent_id.strip()
    seen = {document.document_id}

    while parent:
        found = by_id.get(parent)
        if found is None or found.team_node_id != document.team_node_id:
            return None
        if parent in seen:
            logger.warning(
                "knowledge.tree_cycle_broken",
                document=document.document_id,
                parent=document.parent_id,
            )
            return None
        seen.add(parent)
        if len(seen) > MAX_KNOWLEDGE_TREE_DEPTH:
            logger.info(
                "knowledge.tree_too_deep",
                document=document.document_id,
                depth=len(seen),
            )
            return None
        parent = found.parent_id.strip()

    return document.parent_id.strip() or None


def _node(
    identifier: str,
    by_id: Mapping[str, Document],
    children: Mapping[str, Sequence[str]],
    *,
    depth: int,
) -> TreeNode:
    """Return the subtree rooted at ``identifier``, ordered by title."""
    if depth >= MAX_KNOWLEDGE_TREE_DEPTH:
        return TreeNode(document=by_id[identifier])
    ordered = sorted(children.get(identifier, ()), key=lambda child: by_id[child].title)
    return TreeNode(
        document=by_id[identifier],
        children=tuple(_node(child, by_id, children, depth=depth + 1) for child in ordered),
    )


def flatten(nodes: Iterable[TreeNode]) -> tuple[tuple[Document, int], ...]:
    """Return every document in a forest with its depth, parents before children."""
    found: list[tuple[Document, int]] = []
    for root in nodes:
        found.extend((node.document, depth) for node, depth in root.walk())
    return tuple(found)


@dataclass(slots=True)
class KnowledgeTree:
    """One team's documents, listed and arranged."""

    gateway: PersistenceGateway
    scope: TenantScope

    def __post_init__(self) -> None:
        if not self.scope.team_node_id:
            raise ValueError(
                f"{self.scope.org_id}: the document tree must be scoped to a team — an "
                "unscoped listing is one that shows another team's runbooks"
            )

    async def documents(self, *, limit: int = MAX_QUERY_PAGE_SIZE) -> tuple[Document, ...]:
        """Return this team's documents, most recently updated first.

        The team filter is applied here rather than in the store. No port method
        takes a team — the organisation is the structural boundary — so the
        narrowing within it is this tier's job, and doing it in one place is what
        keeps every caller from having to remember.
        """
        async with self.gateway.begin(self.scope) as uow:
            stored = await uow.knowledge.list_documents(limit=limit)

        return tuple(
            document
            for document in (
                Document.from_stored(record, org_id=self.scope.org_id) for record in stored
            )
            if document.team_node_id == self.scope.team_node_id
        )

    async def tree(self, *, limit: int = MAX_QUERY_PAGE_SIZE) -> tuple[TreeNode, ...]:
        """Return this team's documents as a forest."""
        return build_tree(await self.documents(limit=limit))

    async def place(self, document_id: str, parent_id: str) -> Document:
        """Move a document under ``parent_id`` and return it.

        Raises when the move would make a document its own ancestor. A cycle is
        survivable when it arrives from a sync adapter — the tree breaks it — but
        an operator creating one deliberately has made a mistake worth reporting
        at the moment they make it.
        """
        documents = {document.document_id: document for document in await self.documents()}
        document = documents.get(document_id)
        if document is None:
            raise ValueError(f"{document_id}: this team holds no such document")

        target = parent_id.strip()
        if target:
            if target not in documents:
                raise ValueError(f"{target}: this team holds no such document to file under")
            if _would_cycle(document_id, target, documents):
                raise ValueError(
                    f"filing {document_id!r} under {target!r} would make it its own ancestor"
                )

        moved = replace(document, parent_id=target)
        async with self.gateway.begin(self.scope) as uow:
            await uow.knowledge.upsert_document(moved.to_stored())
        return moved


def _would_cycle(document_id: str, parent_id: str, documents: Mapping[str, Document]) -> bool:
    """Return whether filing a document under a parent closes a loop."""
    seen: set[str] = set()
    current = parent_id
    while current and current not in seen:
        if current == document_id:
            return True
        seen.add(current)
        found = documents.get(current)
        current = found.parent_id.strip() if found else ""
    return False


__all__ = ["KnowledgeTree", "build_tree", "flatten"]
