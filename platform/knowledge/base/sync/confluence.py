"""Confluence pages, as a document source.

The adapter's whole job is the mapping, and each field is a decision:

- **the body** is ``body.storage.value``, the source-of-truth XHTML, rather than
  ``body.view`` — the rendered view has macros expanded into text that reads like
  prose and is not, and a runbook quoting a rendered chart legend is a runbook
  quoting nothing;
- **the parent** is the last ancestor, which is the immediate one in Confluence's
  root-first ordering, so the space's tree survives into the knowledge tree;
- **the location** is the ``webui`` link resolved against the site's base URL,
  because a citation an engineer cannot click is a citation they will not check;
- **the type** comes from the page's labels where a team uses them, and is a
  runbook otherwise, which is what most of a wiki's operational pages are.

No Confluence client is imported. The reader is whatever the deployment already
has — the vendor integration, a script, a fixture — and it hands back page
payloads in the shape the API returns them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from platform.knowledge.base.models import DocumentType
from platform.knowledge.base.sync.port import SourceDocument
from platform.knowledge.base.sync.text import from_html
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: The name this source's documents are namespaced under.
SOURCE = "confluence"


@runtime_checkable
class ConfluenceReader(Protocol):
    """The one read this adapter makes of a Confluence space."""

    async def pages(self) -> Sequence[Mapping[str, Any]]:
        """Return the page payloads this reader is scoped to."""


@dataclass(slots=True)
class ConfluenceSource:
    """Confluence pages as documents."""

    reader: ConfluenceReader
    base_url: str = ""

    @property
    def name(self) -> str:
        """Return the identifier this source's documents are namespaced under."""
        return SOURCE

    async def fetch(self) -> Sequence[SourceDocument]:
        """Return the space's pages as source documents, skipping unusable ones."""
        found: list[SourceDocument] = []
        for page in await self.reader.pages():
            document = self._document(page)
            if document is not None:
                found.append(document)
        logger.info("knowledge.confluence_fetched", pages=len(found))
        return tuple(found)

    def _document(self, page: Mapping[str, Any]) -> SourceDocument | None:
        """Return the source document one page describes, or ``None``."""
        identifier = str(page.get("id", "")).strip()
        if not identifier:
            logger.info("knowledge.confluence_page_without_id")
            return None

        body = from_html(_storage(page))
        if not body.strip():
            # A page with no text is a placeholder, a diagram, or an empty
            # template. Ingesting it would put a title in the index with nothing
            # behind it, which matches everything weakly.
            return None

        return SourceDocument(
            external_id=identifier,
            title=str(page.get("title", "")).strip(),
            body=body,
            source_uri=self._link(page),
            document_type=_type_from_labels(page),
            parent_external_id=_parent(page),
            updated_at=_updated(page),
            tags=_labels(page),
        )

    def _link(self, page: Mapping[str, Any]) -> str:
        """Return the page's URL, absolute where a base URL was configured."""
        links = page.get("_links")
        webui = str(links.get("webui", "")) if isinstance(links, Mapping) else ""
        if not webui:
            return ""
        if not self.base_url:
            return webui
        return f"{self.base_url.rstrip('/')}{webui}"


def _storage(page: Mapping[str, Any]) -> str:
    """Return the page's storage-format body, or ``""``."""
    body = page.get("body")
    if not isinstance(body, Mapping):
        return ""
    storage = body.get("storage")
    if isinstance(storage, Mapping):
        return str(storage.get("value", ""))
    return ""


def _parent(page: Mapping[str, Any]) -> str:
    """Return the immediate ancestor's id, which Confluence lists last."""
    ancestors = page.get("ancestors")
    if not isinstance(ancestors, Sequence) or not ancestors:
        return ""
    last = ancestors[-1]
    return str(last.get("id", "")) if isinstance(last, Mapping) else ""


def _labels(page: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the page's labels, which teams use as their own taxonomy."""
    metadata = page.get("metadata")
    if not isinstance(metadata, Mapping):
        return ()
    labels = metadata.get("labels")
    if not isinstance(labels, Mapping):
        return ()
    results = labels.get("results")
    if not isinstance(results, Sequence):
        return ()
    return tuple(
        str(item.get("name", ""))
        for item in results
        if isinstance(item, Mapping) and item.get("name")
    )


def _type_from_labels(page: Mapping[str, Any]) -> DocumentType:
    """Return the document type a page's labels name, or a runbook.

    Most of a wiki's operational pages are runbooks, and a page labelled
    ``postmortem`` is one an agent should read differently. Anything else falls
    back rather than raising: a team's taxonomy is theirs, and a sync that
    refused a page for using a word this code has not met would be a sync that
    stops.
    """
    for label in _labels(page):
        try:
            return DocumentType(label.strip().lower())
        except ValueError:
            continue
    return DocumentType.RUNBOOK


def _updated(page: Mapping[str, Any]) -> datetime | None:
    """Return when the page was last edited, or ``None`` when it does not say."""
    version = page.get("version")
    if not isinstance(version, Mapping):
        return None
    when = str(version.get("when", ""))
    try:
        return datetime.fromisoformat(when.replace("Z", "+00:00")) if when else None
    except ValueError:
        return None


__all__ = ["SOURCE", "ConfluenceReader", "ConfluenceSource"]
