"""Notion pages, as a document source.

Notion keeps a page's text in a *tree of blocks* rather than in a body field, so
the reader hands back both: the page object, which carries the title, the parent,
the URL, and the edit time, and the page's blocks, which carry the text. The
adapter's job is to turn the second into paragraphs while preserving the two
things a chunker needs — headings and list items.

Rich text is flattened to ``plain_text``. The annotations Notion carries on each
span (bold, colour, code) are formatting rather than content, and a runbook whose
passage arrived with markup would embed it in the model's context for no benefit.
The one exception is a code block, which is fenced, because an indentation-
sensitive command that lost its fence is a command somebody will run wrong.

No Notion client is imported. The reader is whatever the deployment already has.
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
SOURCE = "notion"

#: Block types that become a Markdown heading, at the level Notion names.
_HEADINGS: Mapping[str, int] = {"heading_1": 1, "heading_2": 2, "heading_3": 3}

#: Block types that become a bullet. Numbered items become bullets too: the
#: ordering is in the sequence, and a chunker does not read numerals.
_BULLETS = frozenset({"bulleted_list_item", "numbered_list_item", "to_do"})


@runtime_checkable
class NotionReader(Protocol):
    """The two reads this adapter makes of a Notion workspace."""

    async def pages(self) -> Sequence[Mapping[str, Any]]:
        """Return the page objects this reader is scoped to."""

    async def blocks(self, page_id: str) -> Sequence[Mapping[str, Any]]:
        """Return one page's blocks, in document order."""


@dataclass(slots=True)
class NotionSource:
    """Notion pages as documents."""

    reader: NotionReader

    @property
    def name(self) -> str:
        """Return the identifier this source's documents are namespaced under."""
        return SOURCE

    async def fetch(self) -> Sequence[SourceDocument]:
        """Return the workspace's pages as source documents."""
        found: list[SourceDocument] = []
        for page in await self.reader.pages():
            identifier = str(page.get("id", "")).strip()
            if not identifier:
                continue
            body = from_lines(list(_lines(await self.reader.blocks(identifier))))
            if not body.strip():
                continue
            found.append(
                SourceDocument(
                    external_id=identifier,
                    title=_title(page) or identifier,
                    body=body,
                    source_uri=str(page.get("url", "")),
                    parent_external_id=_parent(page),
                    updated_at=_edited(page),
                )
            )
        logger.info("knowledge.notion_fetched", pages=len(found))
        return tuple(found)


def _plain(rich_text: Any) -> str:
    """Return the plain text a Notion rich-text array carries."""
    if not isinstance(rich_text, Sequence):
        return ""
    return "".join(
        str(span.get("plain_text", "")) for span in rich_text if isinstance(span, Mapping)
    )


def _lines(blocks: Sequence[Mapping[str, Any]]) -> list[str]:
    """Return one line per block, headings and bullets preserved."""
    lines: list[str] = []
    for block in blocks:
        kind = str(block.get("type", ""))
        payload = block.get(kind)
        if not isinstance(payload, Mapping):
            continue
        text = _plain(payload.get("rich_text"))
        if not text.strip():
            continue

        if kind in _HEADINGS:
            lines.extend(("", f"{'#' * _HEADINGS[kind]} {text}", ""))
        elif kind in _BULLETS:
            lines.append(f"- {text}")
        elif kind == "code":
            language = str(payload.get("language", ""))
            lines.extend(("", f"```{language}", text, "```", ""))
        else:
            lines.extend((text, ""))
    return lines


def _title(page: Mapping[str, Any]) -> str:
    """Return a page's title, wherever the property that holds it is named.

    Notion lets a database name its title property anything, so the property is
    found by *type* rather than by name. A lookup on ``"Name"`` works until the
    first team that renamed it, and then silently produces untitled documents.
    """
    properties = page.get("properties")
    if not isinstance(properties, Mapping):
        return ""
    for value in properties.values():
        if isinstance(value, Mapping) and value.get("type") == "title":
            return _plain(value.get("title"))
    return ""


def _parent(page: Mapping[str, Any]) -> str:
    """Return the parent page's id, or ``""`` for a workspace-level page."""
    parent = page.get("parent")
    if not isinstance(parent, Mapping):
        return ""
    return str(parent.get("page_id", ""))


def _edited(page: Mapping[str, Any]) -> datetime | None:
    """Return when the page was last edited, or ``None``."""
    when = str(page.get("last_edited_time", ""))
    try:
        return datetime.fromisoformat(when.replace("Z", "+00:00")) if when else None
    except ValueError:
        return None


__all__ = ["SOURCE", "NotionReader", "NotionSource"]
