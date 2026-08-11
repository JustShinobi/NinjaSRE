"""A document and the resource it is about, joined by name.

A runbook about AdGuard and the container called ``adguard`` are the same thing
seen from two sides. Nothing joins them until something writes the join down,
and an investigation of the resource that has to *know* to go and search for the
document is one that mostly does not.

**The join is by fully-qualified name.** The hostname a workload's tags already
carry and the domain the enrichment already declares. Both appear verbatim in a
document that is about the thing, and both identify exactly one resource.

**Never by display name.** Half of any estate is called something like
``backup``, and a document containing that word would attach itself to a
resource it is not about. A wrong edge costs more than a missing one: the
missing one costs a search, and the wrong one costs an investigation reading a
runbook for a different machine.

**It lives in the graph.** "What touches what" is the topology's question and
the estate has no column for it. The edge runs from the resource to the
document, which is the direction ``edges_from`` walks and the direction the
question is asked in, and its kind is excluded from every dependency traversal
— a document cannot fail, and a blast radius that returned one would be
answering the wrong question.

**A stale link is removed.** A document that stops naming a resource loses its
edge on the next run. An edge pointing at a document *this* run did not see is
left alone, because that is another corpus's link and deleting it would make two
sources silently fight over one resource's panel.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from config.constants.estate import MAX_ESTATE_PAGE_SIZE
from config.constants.knowledge import MAX_DOCUMENTS_PER_RESOURCE
from platform.knowledge.base.models import Document, DocumentType
from platform.observability.logging import get_logger
from platform.persistence.errors import PersistenceError
from platform.persistence.ports.estate_repository import EstateQuery, Resource, whole_estate
from platform.persistence.ports.topology_graph import (
    EdgeKind,
    NodeKind,
    TopologyEdge,
    TopologyNode,
)
from platform.persistence.ports.transaction import PersistenceGateway, TenantScope, UnitOfWork

logger = get_logger(__name__)

#: How a document's graph node is identified. Prefixed for the reason a zone's
#: is: a document called ``adguard`` and a container called ``adguard`` are two
#: nodes rather than one.
DOCUMENT_NODE_PREFIX = "document:"

#: The label prefix a workload's own tags use for the name it answers on. One
#: prefix, in one place, because a label read two ways is a resource nothing
#: links to.
HOST_LABEL_PREFIX = "host-"

#: The attribute the enrichment writes a declared domain into.
DOMAIN_ATTRIBUTE = "domain"

#: Edge properties: which name the document used, and which kind of name it was.
#: On the edge rather than on either node because it is a fact about the pair —
#: two documents can reach one resource by two different names.
MATCHED_PROPERTY = "matched"
MATCHED_ON_PROPERTY = "matched_on"
TITLE_PROPERTY = "title"
LOCATION_PROPERTY = "location"
DOCUMENT_TYPE_PROPERTY = "document_type"


@dataclass(frozen=True, slots=True)
class LinkedDocument:
    """One document a resource is written about in, as a panel shows it."""

    document_id: str
    title: str
    location: str
    document_type: DocumentType = DocumentType.RUNBOOK
    #: The name the document used. Shown beside the entry, because "this is
    #: linked because it says adguard.example.invalid" is what lets an operator
    #: dismiss a link that is wrong.
    matched: str = ""
    #: ``hostname`` or ``domain``.
    matched_on: str = ""


@dataclass(frozen=True, slots=True)
class LinkReport:
    """What one linking pass wrote and unwrote."""

    linked: int = 0
    removed: int = 0
    #: Set when the deployment has no graph store. Zero links and a reason, not
    #: zero links and silence.
    unavailable: str = ""


def match_keys(resource: Resource) -> tuple[tuple[str, str], ...]:
    """Return the names that identify ``resource`` in prose, with their kind.

    Hostnames first, then the declared domain, and each name once. A resource
    whose domain is also its hostname is one fact recorded twice, and the
    hostname is the more specific of the two.
    """
    found: dict[str, str] = {}
    for label in resource.labels:
        if not label.startswith(HOST_LABEL_PREFIX):
            continue
        name = label[len(HOST_LABEL_PREFIX) :].strip().lower()
        if "." in name:
            found.setdefault(name, "hostname")

    domain = str(resource.attributes.get(DOMAIN_ATTRIBUTE, "")).strip().lower()
    if "." in domain:
        found.setdefault(domain, "domain")

    return tuple(found.items())


def mentioned_resources(body: str, resources: Sequence[Resource]) -> tuple[str, ...]:
    """Return the resources ``body`` names, in the order ``resources`` are given.

    In the estate's order rather than in the order the names appear in the text,
    so two runs over one corpus write the same graph and a report of them is a
    readable diff.
    """
    text = body.lower()
    return tuple(
        resource.resource_id
        for resource in resources
        if any(_names(text, key) for key, _ in match_keys(resource))
    )


def matches_for(body: str, resources: Sequence[Resource]) -> tuple[tuple[str, str, str], ...]:
    """Return ``(resource_id, name, kind)`` for every name ``body`` uses.

    One entry per resource — the first of its names the document uses. A
    document that names a resource twice is one link, and which of the two names
    it was is what the panel shows.
    """
    text = body.lower()
    found: list[tuple[str, str, str]] = []
    for resource in resources:
        for key, kind in match_keys(resource):
            if _names(text, key):
                found.append((resource.resource_id, key, kind))
                break
    return tuple(found)


def _names(text: str, key: str) -> bool:
    """Return whether ``text`` uses ``key`` as a name rather than as a fragment.

    Bounded on both sides by something that cannot be part of a hostname, so
    ``not-adguard.example.invalid`` does not match ``adguard.example.invalid``
    and neither does ``adguard.example.invalid.example``. A substring test would
    link a resource to every document about a differently-named machine in the
    same domain.

    The tag form is matched as well as the bare one, because a workload's tag is
    what an operator copies into a runbook when they write down which machine
    they mean.
    """
    return any(
        re.search(rf"(?<![\w.-]){re.escape(form)}(?![\w-])(?!\.[\w-])", text) is not None
        for form in (key, f"{HOST_LABEL_PREFIX}{key}")
    )


@dataclass(frozen=True, slots=True)
class EstateLinker:
    """Writes and reads the join between one team's documents and its estate."""

    gateway: PersistenceGateway
    scope: TenantScope

    async def link(self, documents: Iterable[Document]) -> LinkReport:
        """Write the links ``documents`` imply, and remove the ones they no longer do.

        Never raises into a sync. A deployment without a graph store gets zero
        links and a reason: a corpus that ingested and could not be joined up is
        a different situation from a corpus nothing was written about.
        """
        wanted = tuple(documents)
        if not wanted:
            return LinkReport()

        try:
            async with self.gateway.begin(self.scope) as uow:
                availability = await uow.topology.availability()
                if not availability.available:
                    logger.info("knowledge.estate_link_unavailable", reason=availability.reason)
                    return LinkReport(unavailable=availability.reason or "no graph storage")

                estate = await whole_estate(uow.estate, EstateQuery(limit=MAX_ESTATE_PAGE_SIZE))
                linked = 0
                for document in wanted:
                    for resource_id, name, kind in matches_for(document.body, estate):
                        await self._write(uow, document, resource_id, name, kind)
                        linked += 1

                removed = await self._prune(uow, estate, wanted)
        except PersistenceError as error:
            logger.warning("knowledge.estate_link_failed", error=str(error))
            return LinkReport(unavailable=str(error))

        logger.info("knowledge.estate_linked", linked=linked, removed=removed)
        return LinkReport(linked=linked, removed=removed)

    async def documents_for(self, resource_id: str) -> tuple[LinkedDocument, ...]:
        """Return what has been written about ``resource_id``, by document id.

        An empty tuple when the graph is unavailable. A resource detail panel
        that failed because nobody had written a runbook would be a page that
        does not load for most of any estate.
        """
        try:
            async with self.gateway.begin(self.scope) as uow:
                if not (await uow.topology.availability()).available:
                    return ()
                edges = await uow.topology.edges_from(resource_id, kinds=(EdgeKind.DOCUMENTED_BY,))
        except PersistenceError as error:
            logger.warning("knowledge.estate_link_read_failed", error=str(error))
            return ()

        return tuple(_linked(edge) for edge in edges[:MAX_DOCUMENTS_PER_RESOURCE])

    # -- internals -------------------------------------------------------------

    async def _write(
        self,
        uow: UnitOfWork,
        document: Document,
        resource_id: str,
        name: str,
        kind: str,
    ) -> None:
        """Write one document node and the edge that reaches it."""
        node_id = f"{DOCUMENT_NODE_PREFIX}{document.document_id}"
        await uow.topology.upsert_node(
            TopologyNode(
                node_id=node_id,
                kind=NodeKind.DOCUMENT,
                name=document.title,
                properties={
                    LOCATION_PROPERTY: document.location,
                    DOCUMENT_TYPE_PROPERTY: document.document_type.value,
                },
            )
        )
        await uow.topology.upsert_edge(
            TopologyEdge(
                from_node_id=resource_id,
                to_node_id=node_id,
                kind=EdgeKind.DOCUMENTED_BY,
                properties={
                    MATCHED_PROPERTY: name,
                    MATCHED_ON_PROPERTY: kind,
                    TITLE_PROPERTY: document.title,
                    LOCATION_PROPERTY: document.location,
                    DOCUMENT_TYPE_PROPERTY: document.document_type.value,
                },
            )
        )

    async def _prune(
        self,
        uow: UnitOfWork,
        estate: Sequence[Resource],
        documents: Sequence[Document],
    ) -> int:
        """Delete the links this run's documents no longer imply, and count them."""
        seen = {document.document_id for document in documents}
        current = {
            (resource_id, document.document_id)
            for document in documents
            for resource_id, _, _ in matches_for(document.body, estate)
        }

        removed = 0
        for resource in estate:
            edges = await uow.topology.edges_from(
                resource.resource_id, kinds=(EdgeKind.DOCUMENTED_BY,)
            )
            for edge in edges:
                document_id = edge.to_node_id.removeprefix(DOCUMENT_NODE_PREFIX)
                if document_id not in seen:
                    # Another corpus's link. Not this run's to remove.
                    continue
                if (resource.resource_id, document_id) in current:
                    continue
                await uow.topology.delete_edge(edge)
                removed += 1
        return removed


def _linked(edge: TopologyEdge) -> LinkedDocument:
    """Return one edge as the panel reads it."""
    properties: Mapping[str, object] = edge.properties
    return LinkedDocument(
        document_id=edge.to_node_id.removeprefix(DOCUMENT_NODE_PREFIX),
        title=str(properties.get(TITLE_PROPERTY, "")),
        location=str(properties.get(LOCATION_PROPERTY, "")),
        document_type=DocumentType.parse(str(properties.get(DOCUMENT_TYPE_PROPERTY, ""))),
        matched=str(properties.get(MATCHED_PROPERTY, "")),
        matched_on=str(properties.get(MATCHED_ON_PROPERTY, "")),
    )


__all__ = [
    "DOCUMENT_NODE_PREFIX",
    "DOCUMENT_TYPE_PROPERTY",
    "DOMAIN_ATTRIBUTE",
    "HOST_LABEL_PREFIX",
    "LOCATION_PROPERTY",
    "MATCHED_ON_PROPERTY",
    "MATCHED_PROPERTY",
    "TITLE_PROPERTY",
    "EstateLinker",
    "LinkReport",
    "LinkedDocument",
    "match_keys",
    "matches_for",
    "mentioned_resources",
]
