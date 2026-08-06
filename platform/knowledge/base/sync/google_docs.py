"""Google Docs, as a document source.

A Google document's body is a list of structural elements, each of which is a
paragraph made of text runs. The adapter walks them in order and re-emits
headings as Markdown, which is the one thing the chunker needs and the one thing
the API's own structure makes explicit: a paragraph's ``namedStyleType`` says
``HEADING_1`` where the author used a heading, and that is more reliable than any
inference from formatting.

Tables and embedded objects are skipped rather than flattened. A table rendered
into prose reads as a sentence somebody wrote, and a runbook is exactly the
document where an invented sentence causes harm.

No Google client is imported. The reader is whatever the deployment already has.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from platform.knowledge.base.sync.port import SourceDocument
from platform.knowledge.base.sync.text import from_lines
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: The name this source's documents are namespaced under.
SOURCE = "google-docs"

#: How a document's URL is built from its id. Constructed rather than read,
#: because the API returns the id and every reader would otherwise build the same
#: string slightly differently.
DOCUMENT_URL = "https://docs.google.com/document/d/{document_id}/edit"

#: Named styles that are headings, and the level each becomes.
_HEADING_LEVELS: Mapping[str, int] = {
    "TITLE": 1,
    "HEADING_1": 1,
    "HEADING_2": 2,
    "HEADING_3": 3,
    "HEADING_4": 4,
    "HEADING_5": 5,
    "HEADING_6": 6,
}


@runtime_checkable
class GoogleDocsReader(Protocol):
    """The one read this adapter makes of a Drive folder."""

    async def documents(self) -> Sequence[Mapping[str, Any]]:
        """Return the document resources this reader is scoped to."""


@dataclass(slots=True)
class GoogleDocsSource:
    """Google documents as knowledge-base documents."""

    reader: GoogleDocsReader

    @property
    def name(self) -> str:
        """Return the identifier this source's documents are namespaced under."""
        return SOURCE

    async def fetch(self) -> Sequence[SourceDocument]:
        """Return the folder's documents as source documents."""
        found: list[SourceDocument] = []
        for document in await self.reader.documents():
            identifier = str(document.get("documentId", "")).strip()
            if not identifier:
                continue
            body = from_lines(_lines(document))
            if not body.strip():
                continue
            found.append(
                SourceDocument(
                    external_id=identifier,
                    title=str(document.get("title", "")).strip() or identifier,
                    body=body,
                    source_uri=DOCUMENT_URL.format(document_id=identifier),
                    updated_at=_modified(document),
                )
            )
        logger.info("knowledge.google_docs_fetched", documents=len(found))
        return tuple(found)


def _lines(document: Mapping[str, Any]) -> list[str]:
    """Return one line per paragraph, headings re-emitted as Markdown."""
    body = document.get("body")
    if not isinstance(body, Mapping):
        return []
    content = body.get("content")
    if not isinstance(content, Sequence):
        return []

    lines: list[str] = []
    for element in content:
        if not isinstance(element, Mapping):
            continue
        paragraph = element.get("paragraph")
        if not isinstance(paragraph, Mapping):
            # A table, a section break, or an embedded object. Skipped rather
            # than flattened: a table rendered into prose reads as a sentence
            # somebody wrote.
            continue
        text = _text(paragraph).strip()
        if not text:
            continue
        level = _heading_level(paragraph)
        lines.extend(("", f"{'#' * level} {text}", "") if level else (text, ""))
    return lines


def _text(paragraph: Mapping[str, Any]) -> str:
    """Return the text a paragraph's runs carry, in order."""
    elements = paragraph.get("elements")
    if not isinstance(elements, Sequence):
        return ""
    parts: list[str] = []
    for element in elements:
        if not isinstance(element, Mapping):
            continue
        run = element.get("textRun")
        if isinstance(run, Mapping):
            parts.append(str(run.get("content", "")))
    return "".join(parts)


def _heading_level(paragraph: Mapping[str, Any]) -> int:
    """Return the heading level a paragraph's named style declares, or ``0``."""
    style = paragraph.get("paragraphStyle")
    if not isinstance(style, Mapping):
        return 0
    return _HEADING_LEVELS.get(str(style.get("namedStyleType", "")), 0)


def _modified(document: Mapping[str, Any]) -> datetime | None:
    """Return when the document was last modified, or ``None``."""
    when = str(document.get("modifiedTime", ""))
    try:
        return datetime.fromisoformat(when.replace("Z", "+00:00")) if when else None
    except ValueError:
        return None


__all__ = ["DOCUMENT_URL", "SOURCE", "GoogleDocsReader", "GoogleDocsSource"]
