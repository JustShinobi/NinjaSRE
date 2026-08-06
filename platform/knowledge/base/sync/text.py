"""Turning three vendors' markup into the plain text a chunker can cut.

Every hosted document store keeps its bodies in a shape of its own: Confluence in
an XHTML-ish storage format, Notion in a tree of block objects, Google Docs in a
list of structural elements. None of them is Markdown, and all three have to
become text before chunking can find a heading.

The conversion here is **deliberately crude**, and it is worth saying why rather
than reaching for a parser. What the chunker needs is paragraphs, headings, and
list items, in order. What a full-fidelity conversion would additionally
preserve — tables, macros, embedded diagrams, colour — is content a retrieved
passage cannot use anyway, and every extra rule is a rule that can be wrong about
a page nobody in this repository has seen. A missing table costs a passage; a
mis-parsed body costs the document.

Headings are emitted as Markdown ATX, because that is what ``chunking.sections``
recognises. That is the one place these functions have to be right: a heading
that does not survive is a section boundary the chunker cannot see.
"""

from __future__ import annotations

import re
from html import unescape

#: Confluence block-level tags that end a paragraph. Anything else is inline and
#: is simply dropped, which is what keeps this a stripper rather than a parser.
_BLOCK_END = re.compile(r"</(?:p|div|li|tr|table|ul|ol|h[1-6]|blockquote|pre)>", re.IGNORECASE)

#: Confluence and HTML headings, captured so they can be re-emitted as ATX.
_HEADING = re.compile(r"<h([1-6])[^>]*>(.*?)</h\1>", re.IGNORECASE | re.DOTALL)

#: List items, re-emitted as Markdown bullets so a procedure's steps stay steps.
_LIST_ITEM = re.compile(r"<li[^>]*>(.*?)</li>", re.IGNORECASE | re.DOTALL)

#: A line break in any of its spellings.
_BREAK = re.compile(r"<br\s*/?>", re.IGNORECASE)

#: Any remaining tag, including Confluence's ``ac:`` and ``ri:`` macro elements.
_TAG = re.compile(r"<[^>]+>")

#: Three or more consecutive newlines, collapsed to a paragraph break.
_BLANK_RUN = re.compile(r"\n{3,}")


def from_html(markup: str) -> str:
    """Return the plain text an HTML or Confluence storage body carries.

    Headings become ATX headings and list items become bullets; everything else
    becomes paragraphs. Macros are dropped rather than rendered — a Confluence
    ``ac:structured-macro`` that expands to a live chart at read time has no
    text to contribute, and inventing one would put a sentence in a runbook that
    nobody wrote.
    """
    if not markup.strip():
        return ""

    text = _HEADING.sub(lambda match: f"\n\n{'#' * int(match.group(1))} {match.group(2)}\n", markup)
    text = _LIST_ITEM.sub(lambda match: f"\n- {match.group(1)}", text)
    text = _BREAK.sub("\n", text)
    text = _BLOCK_END.sub("\n\n", text)
    text = _TAG.sub("", text)
    return _tidied(unescape(text))


def from_lines(lines: list[str]) -> str:
    """Return a document assembled from already-plain lines, tidied.

    The Notion and Google Docs adapters both arrive here: their APIs hand back a
    sequence of blocks or elements, each of which is already text once its
    wrapper is unwrapped, and what remains is to join them without leaving a
    dozen blank lines where a dozen empty blocks were.
    """
    return _tidied("\n".join(lines))


def _tidied(text: str) -> str:
    """Return ``text`` with trailing spaces and runs of blank lines removed."""
    stripped = "\n".join(line.rstrip() for line in text.splitlines())
    return _BLANK_RUN.sub("\n\n", stripped).strip() + "\n"


__all__ = ["from_html", "from_lines"]
